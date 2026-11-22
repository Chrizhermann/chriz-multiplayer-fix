-- Multiplayer lobby crash fix (EE 2.7 engines with EEex).
--
-- The Beamdog lobby client (libjingle) runs on its own network thread, and
-- its socket belongs to that thread. Lobby tasks are woken through
-- XmppPump::WakeTasks, which posts "run the tasks" to whichever thread woke
-- them; the compiler also inlined that post into Task::Start and Task::Wake.
-- Wakes from the game's main thread (opening the lobby, refreshing rooms)
-- therefore make the main thread run lobby tasks too. Leaving the lobby
-- (for example "Local network game" -> Load) then tears the client down on
-- both threads at once: the network thread handles the disconnect while the
-- main thread deletes the finished client. Both close and free the same
-- socket, the heap is corrupted, and the game crashes.
--
-- Two small hooks keep every lobby task on the network thread:
--  1. XmppPump::OnMessage (the only place that runs the tasks): on any other
--     OS thread it hands the run to XmppPump::WakeTasks instead.
--  2. XmppPump::WakeTasks: posts to the pump's own network thread.
-- While that thread is not running, everything stays as it was.

CZMP_LobbyFix = CZMP_LobbyFix or { Status = "not initialized" }
local state = CZMP_LobbyFix
if state.queued or state.installed then return end
if not EEex_Active then
    state.Status = "EEex is required"
    print("Multiplayer lobby fix: " .. state.Status)
    return
end

-- Layout, proven by the three patterns in CZMP.db.
local WAKE_HOOK_AT = 0x16              -- in WakeTasks: lea rdx,[rbx-8] ; mov byte ptr [rsp+20h],0
local ON_MESSAGE = 0xB0                -- XmppPump::OnMessage: add rcx,8 ; xor edx,edx ; jmp RunTasks
local PUMP_NOTIFY = 0x88               -- XmppPump::notify_ (the owning XmppThread + 0x110)
local NOTIFY_PUMP = 0x10               -- XmppThread::pump_ (+0x120), seen from notify_
local NOTIFY_THREAD = 0x110            -- XmppThread (talk_base::Thread) = notify_ - 0x110
local NOTIFY_STARTED = 0x110 - 0xFC    -- talk_base::Thread::started_, below notify_
local NOTIFY_THREAD_ID = 0x110 - 0x108 -- talk_base::Thread::thread_id_, below notify_

local function expectBytes(address, bytes, what)
    for i, byte in ipairs(bytes) do
        if EEex_ReadU8(address + i - 1) ~= byte then
            error(what .. " changed or another mod already hooked it")
        end
    end
end

local function install()
    local wake = EEex_TryLabel("CZMP-XmppPump::WakeTasks")
    if not wake then error("the lobby task pump was not found") end
    if not EEex_TryLabel("CZMP-XmppThread::XmppThread") then error("the lobby thread layout was not found") end
    if not EEex_TryLabel("CZMP-talk_base::Thread::Start") then error("the network thread layout was not found") end
    local onMessage = wake + ON_MESSAGE
    expectBytes(wake + WAKE_HOOK_AT, { 0x48,0x8D,0x53,0xF8, 0xC6,0x44,0x24,0x20,0x00, 0x45,0x33,0xC9 }, "the lobby wake-up")
    expectBytes(onMessage, { 0x48,0x83,0xC1,0x08, 0x33,0xD2, 0xE9 }, "the lobby task runner")

    local counters = EEex_Malloc(16)
    EEex_WritePtr(counters, 0)
    EEex_WritePtr(counters + 8, 0)
    state.counters = counters

    EEex_DisableCodeProtection()
    local ok, err = pcall(function()
        -- 1. WakeTasks: rbx = the pump's TaskRunner part (pump + 8), rax = the current thread.
        EEex_HookBeforeRestoreWithLabels(wake + WAKE_HOOK_AT, 0, 9, 9, {
            { "hook_integrity_watchdog_ignore_registers", {
                EEex_HookIntegrityWatchdogRegister.RAX, EEex_HookIntegrityWatchdogRegister.RCX,
                EEex_HookIntegrityWatchdogRegister.R10, EEex_HookIntegrityWatchdogRegister.R11 } },
        }, { [[
            mov r10, qword ptr ds:[rbx+]], PUMP_NOTIFY - 8, [[]
            test r10, r10
            jz czmp_wake_keep
            lea rcx, qword ptr ds:[rbx-8]
            cmp qword ptr ds:[r10+]], NOTIFY_PUMP, [[], rcx
            jne czmp_wake_keep
            cmp byte ptr ds:[r10-]], NOTIFY_STARTED, [[], 0
            je czmp_wake_keep
            lea r10, qword ptr ds:[r10-]], NOTIFY_THREAD, [[]
            cmp rax, r10
            je czmp_wake_keep
            mov rax, r10
            mov r11, ]], counters, [[ #ENDL
            lock inc qword ptr ds:[r11]
            czmp_wake_keep:
        ]] })

        -- 2. OnMessage: rcx = the pump. Run its tasks only on its own network thread.
        EEex_HookBeforeRestoreWithLabels(onMessage, 0, 6, 6, {
            { "manual_hook_integrity_exit", true },
            { "czmp_wake_tasks", wake },
            { "hook_integrity_watchdog_ignore_registers", {
                EEex_HookIntegrityWatchdogRegister.RCX,
                EEex_HookIntegrityWatchdogRegister.R10, EEex_HookIntegrityWatchdogRegister.R11 } },
        }, { [[
            mov r10, qword ptr ds:[rcx+]], PUMP_NOTIFY, [[]
            test r10, r10
            jz czmp_run_here
            cmp qword ptr ds:[r10+]], NOTIFY_PUMP, [[], rcx
            jne czmp_run_here
            cmp byte ptr ds:[r10-]], NOTIFY_STARTED, [[], 0
            je czmp_run_here
            mov r11d, dword ptr gs:[0x48]
            cmp dword ptr ds:[r10-]], NOTIFY_THREAD_ID, [[], r11d
            je czmp_run_here
            mov r10, ]], counters + 8, [[ #ENDL
            lock inc qword ptr ds:[r10]
            lea rcx, qword ptr ds:[rcx+8]
            #MANUAL_HOOK_EXIT(1)
            jmp #L(czmp_wake_tasks)
            czmp_run_here:
            #MANUAL_HOOK_EXIT(0)
        ]] })
    end)
    EEex_EnableCodeProtection()
    if not ok then error(err) end
    if EEex_ReadU8(wake + WAKE_HOOK_AT) ~= 0xE9 or EEex_ReadU8(onMessage) ~= 0xE9 then
        error("the hooks did not take")
    end
    state.address = wake
    return true
end

-- Console aid: wake-ups sent to the network thread, task runs handed over to it.
function CZMP_LobbyFix.GetCounts()
    if not state.counters then return 0, 0 end
    return EEex_Read64(state.counters), EEex_Read64(state.counters + 8)
end

state.queued = true
EEex_GameState_AddInitializedListener(function()
    local ok, err = pcall(install)
    state.installed = ok and err == true
    state.Status = state.installed and "active" or tostring(err)
    pcall(print, "Multiplayer lobby fix: " .. state.Status)
end)
