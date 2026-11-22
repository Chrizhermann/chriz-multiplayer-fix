-- Save copy button: copies a save between the single-player and the
-- multiplayer save folders, from the game's Load screen.
--
-- On the multiplayer Load screen it copies a save into the single-player
-- saves, on the single-player Load screen into the multiplayer saves. The
-- original stays where it is; the copy gets the next free slot number in the
-- other folder, so nothing is ever overwritten. Files are copied with the
-- Windows file functions, so no console window opens.

CZMS = CZMS or {}
local state = CZMS
if state.queued then return end
if not EEex_Active then
    print("Save copy button: EEex is required")
    return
end

-- The copy uses LuaJIT's FFI, which EEex has when it runs on LuaJIT.
local hasFfi, ffi = pcall(require, "ffi")
if not hasFfi then
    print("Save copy button: inactive; it needs EEex running on LuaJIT")
    return
end
local BS = string.char(92)

local TEXT = {
    CZMS_TO_SP = "Copy to single player",
    CZMS_TO_MP = "Copy to multiplayer",
    CZMS_COPY = "Copy",
    CZMS_ASK_TO_SP = "Copy the save \"%s\" (%s) to the single-player saves?\n\nThe multiplayer save stays as it is.",
    CZMS_ASK_TO_MP = "Copy the save \"%s\" (%s) to the multiplayer saves?\n\nThe single-player save stays as it is.",
    CZMS_DONE_TO_SP = "Copied. Load \"%s\" from Single Player > Load Game.",
    CZMS_DONE_TO_MP = "Copied. Load \"%s\" from Multiplayer > Load Game.",
    CZMS_FAILED = "The save could not be copied: %s\n\nNothing was changed.",
    CZMS_FAILED_LEFT = "The save could not be copied: %s\n\nThis unfinished copy could not be removed; please delete it:\n%s",
}

-- Texts come from this table, so a language change (which replaces the
-- game's uiStrings) cannot turn them into raw keys. uiStrings gets them too,
-- for the popup button label, after every load of the game's texts.
local function text(key)
    return TEXT[key]
end

local function addUiStrings()
    if type(uiStrings) ~= "table" then return end
    for key, value in pairs(TEXT) do uiStrings[key] = value end
end

-------------------------------------------------------------------------------
-- Windows file functions
-------------------------------------------------------------------------------

pcall(ffi.cdef, [[
typedef struct { unsigned long Data1; unsigned short Data2; unsigned short Data3; unsigned char Data4[8]; } CZMS_GUID;
typedef struct { unsigned long dwLowDateTime; unsigned long dwHighDateTime; } CZMS_FILETIME;
typedef struct {
    unsigned long dwFileAttributes;
    CZMS_FILETIME ftCreationTime, ftLastAccessTime, ftLastWriteTime;
    unsigned long nFileSizeHigh, nFileSizeLow, dwReserved0, dwReserved1;
    wchar_t cFileName[260];
    wchar_t cAlternateFileName[14];
} CZMS_FIND_DATAW;
int SHGetKnownFolderPath(const CZMS_GUID* rfid, unsigned long dwFlags, void* hToken, wchar_t** ppszPath);
void CoTaskMemFree(void* pv);
int WideCharToMultiByte(unsigned int cp, unsigned long flags, const wchar_t* w, int cw, char* m, int cm, const char* d, int* u);
int MultiByteToWideChar(unsigned int cp, unsigned long flags, const char* m, int cm, wchar_t* w, int cw);
unsigned long GetFileAttributesW(const wchar_t* path);
int CreateDirectoryW(const wchar_t* path, void* security);
int RemoveDirectoryW(const wchar_t* path);
int CopyFileW(const wchar_t* from, const wchar_t* to, int failIfExists);
int DeleteFileW(const wchar_t* path);
void* FindFirstFileW(const wchar_t* pattern, CZMS_FIND_DATAW* data);
int FindNextFileW(void* handle, CZMS_FIND_DATAW* data);
int FindClose(void* handle);
unsigned long GetLastError(void);
]])

local kernel32 = ffi.C
local INVALID_ATTRIBUTES = 0xFFFFFFFF
local ATTRIBUTE_DIRECTORY = 0x10
local INVALID_HANDLE = ffi.cast("void*", -1)

local function toWide(s)
    local n = kernel32.MultiByteToWideChar(65001, 0, s, -1, nil, 0)
    local buffer = ffi.new("wchar_t[?]", n)
    kernel32.MultiByteToWideChar(65001, 0, s, -1, buffer, n)
    return buffer
end

local function fromWide(w)
    local n = kernel32.WideCharToMultiByte(65001, 0, w, -1, nil, 0, nil, nil)
    local buffer = ffi.new("char[?]", n)
    kernel32.WideCharToMultiByte(65001, 0, w, -1, buffer, n, nil, nil)
    return ffi.string(buffer)
end

local function isDirectory(path)
    local attributes = kernel32.GetFileAttributesW(toWide(path))
    return attributes ~= INVALID_ATTRIBUTES and bit.band(attributes, ATTRIBUTE_DIRECTORY) ~= 0
end

-- Entries of a folder: { name = ..., directory = true/false }.
local function listFolder(path)
    local entries = {}
    local data = ffi.new("CZMS_FIND_DATAW")
    local handle = kernel32.FindFirstFileW(toWide(path .. BS .. "*"), data)
    if handle == INVALID_HANDLE then return entries end
    repeat
        local name = fromWide(data.cFileName)
        if name ~= "." and name ~= ".." then
            entries[#entries + 1] = {
                name = name,
                directory = bit.band(data.dwFileAttributes, ATTRIBUTE_DIRECTORY) ~= 0,
            }
        end
    until kernel32.FindNextFileW(handle, data) == 0
    kernel32.FindClose(handle)
    return entries
end

-- The game keeps its saves in Documents\<engine name>, like Beamdog's own
-- launcher: the Documents folder Windows reports (also when OneDrive moved it).
local function profileFolder()
    local shell32 = ffi.load("shell32")
    local ole32 = ffi.load("ole32")
    local documentsId = ffi.new("CZMS_GUID", { 0xFDD39AD0, 0x238F, 0x46AF,
        { 0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7 } })
    local result = ffi.new("wchar_t*[1]")
    if shell32.SHGetKnownFolderPath(documentsId, 0, nil, result) ~= 0 then return nil end
    local documents = fromWide(result[0])
    ole32.CoTaskMemFree(result[0])
    if type(engine_name) ~= "string" or engine_name == "" then return nil end
    return documents .. BS .. engine_name
end

-------------------------------------------------------------------------------
-- Copying
-------------------------------------------------------------------------------

-- "000000052-Name" -> 52, "Name"
local function splitSaveFolder(folder)
    local number, name = folder:match("^(%d+)%-(.*)$")
    return tonumber(number), name or folder
end

local function exists(path)
    return kernel32.GetFileAttributesW(toWide(path)) ~= INVALID_ATTRIBUTES
end

-- The creation time of a file in Unix seconds, or nil.
local function creationTime(path)
    local data = ffi.new("CZMS_FIND_DATAW")
    local handle = kernel32.FindFirstFileW(toWide(path), data)
    if handle == INVALID_HANDLE then return nil end
    kernel32.FindClose(handle)
    local ticks = data.ftCreationTime.dwHighDateTime * 4294967296 + data.ftCreationTime.dwLowDateTime
    return math.floor(ticks / 10000000) - 11644473600
end
CZMS.CreationTime = creationTime

local function nextFreeFolder(targetRoot, name)
    local highest = 1 -- 0 and 1 are the auto and quick save slots
    for _, entry in ipairs(listFolder(targetRoot)) do
        if entry.directory then
            local number = splitSaveFolder(entry.name)
            if number and number > highest then highest = number end
        end
    end
    return string.format("%09d-%s", highest + 1, name)
end

-- Copies the save folder fileName out of "save" (toMultiplayer) or "mpsave".
-- fileTime is the time the Load screen shows for the save (the creation time
-- of its BALDUR.gam): the folder is copied only when it is that very save, so
-- a save from another list (a Black Pits save in bpsave, say) whose folder
-- has the same name as one in "save" is never copied in its place.
-- Returns the new folder name, or nil, a reason and the path of an
-- unfinished copy that could not be removed (if any).
CZMS.ProfileFolder = profileFolder

function CZMS.CopySave(fileName, toMultiplayer, fileTime)
    local profile = CZMS.ProfileFolder()
    if not profile then return nil, "the game's profile folder was not found" end
    local sourceRoot = profile .. BS .. (toMultiplayer and "save" or "mpsave")
    local targetRoot = profile .. BS .. (toMultiplayer and "mpsave" or "save")
    local source = sourceRoot .. BS .. fileName
    local mode = toMultiplayer and "single-player" or "multiplayer"
    if not isDirectory(source) then
        return nil, "it is not one of the " .. mode .. " saves in " .. sourceRoot
    end
    local created = creationTime(source .. BS .. "BALDUR.gam")
    if tonumber(fileTime) and not (created and math.abs(created - tonumber(fileTime)) <= 1) then
        return nil, "it is not one of the " .. mode .. " saves in " .. sourceRoot
    end
    if not isDirectory(targetRoot) and kernel32.CreateDirectoryW(toWide(targetRoot), nil) == 0 then
        return nil, "the folder " .. targetRoot .. " could not be created"
    end

    local _, name = splitSaveFolder(fileName)
    local folder = nextFreeFolder(targetRoot, name)
    local target = targetRoot .. BS .. folder
    if kernel32.CreateDirectoryW(toWide(target), nil) == 0 then
        return nil, "the folder " .. target .. " could not be created (error " .. tonumber(kernel32.GetLastError()) .. ")"
    end

    local written = {}
    local failure
    for _, entry in ipairs(listFolder(source)) do
        if not entry.directory then
            local to = target .. BS .. entry.name
            -- A failed copy can leave a partial file behind: it is removed too.
            written[#written + 1] = to
            if kernel32.CopyFileW(toWide(source .. BS .. entry.name), toWide(to), 1) == 0 then
                failure = entry.name .. " (error " .. tonumber(kernel32.GetLastError()) .. ")"
                break
            end
        end
    end
    if failure or #written == 0 then
        for _, path in ipairs(written) do
            if exists(path) then kernel32.DeleteFileW(toWide(path)) end
        end
        kernel32.RemoveDirectoryW(toWide(target))
        local reason = failure and ("copying " .. failure .. " failed") or "the save folder is empty"
        return nil, reason, exists(target) and target or nil
    end
    print(string.format("Save copy button: %s -> %s", source, target))
    return folder
end

-------------------------------------------------------------------------------
-- The Load screen buttons
-------------------------------------------------------------------------------
-- The Load screen comes in two layouts:
--  * rows (IWD:EE): every row has its own Load and Delete buttons. Each row
--    gets a small Copy button, left of the party portraits.
--  * list (BG:EE, BG2:EE, EET): the player selects a save in a list and the
--    Load button at the bottom loads it. The bottom row gets a Copy button
--    that works on the selected save, like Load and Delete.

local function intoMultiplayer()
    return not e:IsMultiplayer()
end

-- Hidden while BG2:EE imports a BG:EE save: the Load screen then lists the
-- other game's saves.
function CZMS.Available()
    return not (type(gameSaves) == "table" and gameSaves.isImporting == 1)
end

local function saveFiles()
    local files = gameSaves and gameSaves.files
    return type(files) == "table" and files or {}
end

local function rowSave(row)
    return saveFiles()[row + (tonumber(loadSaveOffset) or 0)]
end

local function selectedSave()
    return type(currentSave) == "number" and saveFiles()[currentSave] or nil
end

local function askAndCopy(save)
    local toMultiplayer = intoMultiplayer()
    local name = save.slotName or save.fileName
    local when = ((save.chapter or "") .. " " .. (save.time or "")):gsub("^%s+", ""):gsub("%s+$", "")
    local question = string.format(text(toMultiplayer and "CZMS_ASK_TO_MP" or "CZMS_ASK_TO_SP"), name, when)
    addUiStrings()
    popup2Button(question, "CZMS_COPY", function()
        local ok, folder, reason, left = pcall(CZMS.CopySave, save.fileName, toMultiplayer, save.fileTime)
        if ok and folder then
            popupInfo(string.format(text(toMultiplayer and "CZMS_DONE_TO_MP" or "CZMS_DONE_TO_SP"), name))
        else
            local why = ok and reason or tostring(folder)
            print("Save copy button: " .. why .. (left and (" (left behind: " .. left .. ")") or ""))
            if left then
                popupInfo(string.format(text("CZMS_FAILED_LEFT"), why, left))
            else
                popupInfo(string.format(text("CZMS_FAILED"), why))
            end
        end
    end, "CANCEL_BUTTON")
end

function CZMS.ButtonText()
    return text(intoMultiplayer() and "CZMS_TO_MP" or "CZMS_TO_SP")
end

function CZMS.CopyText()
    return text("CZMS_COPY")
end

function CZMS.SelectedClickable()
    return selectedSave() ~= nil
end

function CZMS.SelectedAction()
    local save = selectedSave()
    if save and CZMS.Available() then askAndCopy(save) end
end

function CZMS.RowEnabled(row)
    return rowSave(row) ~= nil and CZMS.Available()
end

function CZMS.RowAction(row)
    local save = rowSave(row)
    if save and CZMS.Available() then askAndCopy(save) end
end

-- Menu geometry.
local function eachItem(menu)
    local item = menu.items
    return function()
        local current = item
        if current then item = current.next end
        return current
    end
end

local function isBig(area)
    return area.w >= 700 or area.h >= 300
end

local function hasBam(item)
    return item.type == uiItemType.ITEM_BUTTON and EEex_Menu_GetItemVariant(item.bam.resref) ~= nil
end

local function isFree(menu, x, y, w, h)
    for item in eachItem(menu) do
        local a = item.area
        if not isBig(a) and x < a.x + a.w + 4 and x + w > a.x - 4 and y < a.y + a.h and y + h > a.y then
            return false
        end
    end
    return true
end

-- Rows: the save thumbnails at the left edge, one per row.
local function findRows(menu)
    local rows = {}
    for item in eachItem(menu) do
        local a = item.area
        if item.type == uiItemType.ITEM_BUTTON and a.x < 100 and a.w >= 140 and a.h >= 100 and not isBig(a) then
            rows[#rows + 1] = { x = a.x, y = a.y, w = a.w, h = a.h }
        end
    end
    table.sort(rows, function(r1, r2) return r1.y < r2.y end)
    return rows
end

-- In a row the text starts right of the thumbnail, the party portraits sit
-- below the text, and the row's Load button sits at the right.
local function rowSpot(menu, row)
    local textX, slotX, slotY, slotH, load
    for item in eachItem(menu) do
        local a = item.area
        if a.y >= row.y and a.y < row.y + row.h and a.x > row.x + row.w and not isBig(a) then
            local button = item.type == uiItemType.ITEM_BUTTON
            if not button and (not textX or a.x < textX) then textX = a.x end
            if button and a.w <= 40 and a.h >= 30 and (not slotX or a.x < slotX) then
                slotX, slotY, slotH = a.x, a.y, a.h
            end
            if hasBam(item) and a.w >= 120 and a.h >= 30 and a.h <= 70 and (not load or a.y < load.area.y) then
                load = item
            end
        end
    end
    if not (textX and slotX and load) then return nil end
    local h = load.area.h
    local spot = { x = textX, y = slotY + math.floor((slotH - h) / 2), w = slotX - 8 - textX, h = h, model = load }
    if spot.w < 80 then return nil end
    return spot
end

local function screenWidth(menu)
    local width = 0
    for item in eachItem(menu) do width = math.max(width, item.area.x + item.area.w) end
    return width > 0 and width or 1024
end

-- The bottom row: the lowest styled button (Cancel) is the model. First
-- choice is its mirror image, so the row stays symmetric; otherwise the
-- leftmost free spot, shrunk a little if needed.
local function bottomSpot(menu)
    local model
    for item in eachItem(menu) do
        local a = item.area
        if hasBam(item) and a.w >= 120 and a.h >= 30 and a.h <= 70 and (not model or a.y > model.area.y) then
            model = item
        end
    end
    if not model then return nil end
    local m = model.area
    local screen = screenWidth(menu)
    for _, scale in ipairs({ 1, 0.92, 0.85, 0.8 }) do
        local w = math.floor(m.w * scale)
        local candidates = { screen - m.x - w }
        for x = 12, screen - w - 12, 2 do candidates[#candidates + 1] = x end
        for _, x in ipairs(candidates) do
            if x >= 12 and x + w <= screen - 12 and isFree(menu, x, m.y, w, m.h) then
                return { x = x, y = m.y, w = w, h = m.h, model = model }
            end
        end
    end
    return { x = 12, y = m.y - m.h - 6, w = m.w, h = m.h, model = model }
end

local function inject(template, id, spot)
    local button = EEex_Menu_InjectTemplateInstance("LOAD", template, id, spot.x, spot.y, spot.w, spot.h)
    local model = spot.model
    button.bam.resref = model.bam.resref
    button.bam.sequence = model.bam.sequence
    button.bam.scaletoclip = spot.w < model.area.w and 1 or 0
    button.pad.x, button.pad.y, button.pad.w, button.pad.h = model.pad.x, model.pad.y, model.pad.w, model.pad.h
end

-- All spots are worked out before the first button goes in, so the new
-- buttons never stand in each other's way.
local function install()
    local menu = EEex_Menu_Find("LOAD")
    if not menu then
        print("Save copy button: the Load screen was not found")
        return
    end
    local layout = { kind = "none", spots = {} }
    CZMS.Layout = layout

    local rows = findRows(menu)
    local spots = {}
    for i, row in ipairs(rows) do
        local spot = rowSpot(menu, row)
        if not spot or not isFree(menu, spot.x, spot.y, spot.w, spot.h) then
            spots = {}
            break
        end
        spots[i] = spot
    end
    if #rows > 0 and #spots == #rows then
        layout.kind = "rows"
        for i, spot in ipairs(spots) do
            inject("CZMS_TEMPLATE_RowButton", i, spot)
            layout.spots[i] = string.format("%d %d %d %d", spot.x, spot.y, spot.w, spot.h)
        end
        return
    end

    local spot = bottomSpot(menu)
    if not spot then
        print("Save copy button: no place for the button on the Load screen")
        return
    end
    layout.kind = "list"
    inject("CZMS_TEMPLATE_SelectedButton", 1, spot)
    layout.spots[1] = string.format("%d %d %d %d", spot.x, spot.y, spot.w, spot.h)
end

state.queued = true
if EEex_Menu_AddTranslationLoadedListener then
    EEex_Menu_AddTranslationLoadedListener(addUiStrings)
end
EEex_Menu_AddAfterMainFileLoadedListener(function()
    addUiStrings()
    EEex_Menu_LoadFile("CZMS")
    local ok, err = pcall(install)
    if not ok then print("Save copy button: " .. tostring(err)) end
end)
