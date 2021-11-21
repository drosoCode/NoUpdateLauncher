from winreg import ConnectRegistry, OpenKey, QueryValueEx, HKEY_CURRENT_USER
from steam.client.cdn import CDNClient
from steam.client import SteamClient
import os
import subprocess
import vdf
import json
import argparse
import PySimpleGUI as sg
from appdirs import user_data_dir
import requests
import winshell
from win32com.client import Dispatch
import sys

# run pyinstaller -F main.py   to create an executable file

basePath = user_data_dir(appname="NoUpdateLauncher", appauthor="drosocode")
CONFIG_FILE = os.path.join(basePath, "settings.json")

# ensure that the config file exists
if not os.path.exists(basePath):
    os.makedirs(basePath)
if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "w+") as f:
        f.write("{}")


with open(CONFIG_FILE, "r") as f:
    config = json.load(f)


def getSteamInstallDir():
    return QueryValueEx(
        OpenKey(ConnectRegistry(None, HKEY_CURRENT_USER), r"SOFTWARE\Valve\Steam"),
        "SteamPath",
    )[0]


def getSteamLibraries(steamDir):
    libs = [steamDir]
    with open(os.path.join(steamDir, "steamapps", "libraryfolders.vdf"), "r") as f:
        data = vdf.load(f)["libraryfolders"]
        i = 1
        while True:
            if str(i) in data:
                libs.append(data[str(i)]["path"])
                i += 1
            else:
                break
    return libs


def listGames(steamLibraries):
    games = {}
    for lib in steamLibraries:
        base = os.path.join(lib, "steamapps")
        for file in os.listdir(base):
            if file.endswith(".acf"):
                with open(os.path.join(base, file), "r") as f:
                    gameData = vdf.load(f)["AppState"]

                    installedDepots = {}
                    if "InstalledDepots" in gameData:
                        for i in gameData["InstalledDepots"].items():
                            installedDepots[i[0]] = i[1]["manifest"]

                    games[gameData["appid"]] = {
                        "name": gameData["name"],
                        "libraryPath": lib,
                        "currentlyInstalledDepots": installedDepots,  # the real depots that are currently installed
                        "mode": 0,
                        "branch": "public",
                    }
    return games


def getInstalledDepots(appid):
    p = os.path.join(
        config[appid]["libraryPath"], "steamapps", f"appmanifest_{appid}.acf"
    )
    installedDepots = {}
    with open(p, "r") as f:
        gameData = vdf.load(f)["AppState"]

        if "InstalledDepots" in gameData:
            for i in gameData["InstalledDepots"].items():
                installedDepots[i[0]] = i[1]["manifest"]

    return installedDepots


def getIconForApp(appid):
    data = requests.get(f"https://api.steamcmd.net/v1/info/{appid}").json()
    hash = data["data"][appid]["common"]["clienticon"]
    return f"https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/{appid}/{hash}.ico"


def createShortcut(appid):
    if getattr(sys, "frozen", False):
        fileName = sys.executable
    else:
        fileName = __file__

    path = os.path.join(winshell.desktop(), "[NUL] " + config[appid]["name"] + ".lnk")
    pathToExeDir = os.getcwd()
    shell = Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(path)
    shortcut.Targetpath = os.path.join(pathToExeDir, fileName)
    shortcut.Arguments = " -a " + appid
    shortcut.WorkingDirectory = pathToExeDir
    shortcut.IconLocation = getIconForApp(appid)
    shortcut.save()


def getManifestsForApp(appid, branch="public"):
    client = SteamClient()
    client.anonymous_login()
    cdn = CDNClient(client)
    return cdn.get_manifests(int(appid), branch=branch, decrypt=False)


def run(appid, start=True):
    print(f"run: {appid}")
    game = config.get(appid)
    if game is None:
        print(f"Game {appid} is not tracked")
        if start:
            runSteamGame(appid)
        exit()
    else:
        updateAvailable = False
        newUpdate = False
        updateSelect = None
        fakedDepots = getInstalledDepots(appid)
        newestDepots = {}
        for i in getManifestsForApp(appid, game["branch"]):
            depotID = str(i.depot_id)
            depotManifest = str(i.gid)
            if (
                depotID in game["currentlyInstalledDepots"]
                and fakedDepots[depotID] != game["currentlyInstalledDepots"][depotID]
            ):
                # if the faked depots doesnt corresponds to the currently installed depots, then there are some updates that are missing
                updateAvailable = True

            if depotID in fakedDepots and depotManifest != fakedDepots[depotID]:
                # if the faked depots doesnt correpsonds to the newest depots, then there is a new update available
                newUpdate = True

            newestDepots[depotID] = depotManifest

        if updateAvailable or newUpdate:
            print("update available")
            if newUpdate:
                print("this is a new update")
            if game["mode"] == 0 or (game["mode"] == 1 and newUpdate):
                # show prompt
                updateSelect = askUpdateWindow(game["name"], newUpdate)
                if updateSelect == 1:
                    # write new manifest ids to fake the update
                    applyDepots(appid, newestDepots)
                    print("update faked")
                elif updateSelect == 0:
                    # let the game update
                    print("update allowed")
                    applyDepots(appid, game["currentlyInstalledDepots"])
                    # save the game as updated
                    game["currentlyInstalledDepots"] = newestDepots
            else:
                # just fake the update and launch the game
                # write new manifest ids to fake the update
                applyDepots(appid, newestDepots)
                print("update faked")
        else:
            print("no available update")

        # save changes and start the game
        if updateSelect != -1:
            config[appid] = game
            saveConfig()
            if start:
                runSteamGame(appid)


def runSteamGame(appid):
    subprocess.run(f"cmd /c start steam://run/{appid}")


def restartSteam():
    os.system("taskkill /f /im steam.exe")
    subprocess.Popen(os.path.join(getSteamInstallDir(), "steam.exe"))


def applyDepots(appid, depots):
    p = os.path.join(
        config[appid]["libraryPath"], "steamapps", f"appmanifest_{appid}.acf"
    )
    with open(p, "r") as f:
        data = vdf.load(f)

    changes = False
    for i in data["AppState"]["InstalledDepots"]:
        if data["AppState"]["InstalledDepots"][i]["manifest"] != depots[i]:
            changes = True
            data["AppState"]["InstalledDepots"][i]["manifest"] = depots[i]

    if changes:
        with open(p, "w") as f:
            vdf.dump(data, f)
        askRestartSteam()


def setUpdateMode(appid, mode):
    p = os.path.join(
        config[appid]["libraryPath"], "steamapps", f"appmanifest_{appid}.acf"
    )
    with open(p, "r") as f:
        data = vdf.load(f)

    if data["AppState"]["StateFlags"] != str(mode):
        data["AppState"]["StateFlags"] = str(mode)

        with open(p, "w") as f:
            vdf.dump(data, f)
        askRestartSteam()


def mainWindow():
    layout = []
    games = listGames(getSteamLibraries(getSteamInstallDir()))
    for g in games.items():
        status = "Enable"
        color = ("white", "red")
        mode = -1
        disabled = True
        if g[0] in config:
            status = "Disable"
            color = ("white", "green")
            mode = config[g[0]]["mode"]
            disabled = False

        layout.append(
            [
                sg.Text(g[1]["name"]),
                sg.Text(g[0]),
                sg.Button(status, button_color=color, key=g[0] + "_enable"),
                sg.Button(
                    f"Mode [{mode}]",
                    disabled=disabled,
                    key=g[0] + "_mode",
                ),
                sg.Button(
                    f"Branch",
                    disabled=disabled,
                    key=g[0] + "_branch",
                ),
                sg.Button(
                    f"Create Shortcut",
                    disabled=disabled,
                    key=g[0] + "_shortcut",
                ),
                sg.Button("Play", key=g[0] + "_run"),
                sg.Button("Check Updates", key=g[0] + "_update", disabled=disabled),
            ]
        )

    size = (800, 400)
    window = sg.Window(
        "NoUpdate Launcher",
        [[sg.Column(layout, size=size, scrollable=True)]],
        size=size,
    )

    # Display and interact with the Window using an Event Loop
    while True:
        event, values = window.read()
        if event == sg.WINDOW_CLOSED:
            window.close()
            break
        else:
            p = event.find("_")
            appid = event[0:p]
            widgetType = event[p + 1 :]
            widget = window[event]

            if widgetType == "enable":
                if widget.ButtonText == "Enable":
                    # enable the game
                    mode = selectMode()
                    if mode != -1:
                        config[appid] = games[appid]
                        config[appid]["mode"] = mode
                        # ensure that the update settings are set to "update only when launching the game"
                        setUpdateMode(appid, 4)
                        # update ui
                        widget.update("Disable", button_color=("white", "green"))
                        window[appid + "_mode"].update(f"Mode [{mode}]", disabled=False)
                        window[appid + "_update"].update(disabled=False)
                        window[appid + "_branch"].update(disabled=False)
                        window[appid + "_shortcut"].update(disabled=False)
                else:
                    # disable the game
                    applyDepots(appid, config[appid]["currentlyInstalledDepots"])
                    del config[appid]
                    # update ui
                    widget.update("Enable", button_color=("white", "red"))
                    window[appid + "_mode"].update(disabled=True)
                    window[appid + "_branch"].update(disabled=True)
                    window[appid + "_shortcut"].update(disabled=True)
                    window[appid + "_update"].update(disabled=True)

                saveConfig()

            elif widgetType == "run":
                run(appid)

            elif widgetType == "update":
                run(appid, False)

            elif widgetType == "mode":
                mode = selectMode()
                if mode != -1:
                    config[appid]["mode"] = mode
                    window[appid + "_mode"].update(f"Mode [{mode}]")
                    saveConfig()

            elif widgetType == "branch":
                branch = selectBranch(config[appid]["branch"])
                if branch != -1:
                    config[appid]["branch"] = branch
                    saveConfig()

            elif widgetType == "shortcut":
                createShortcut(appid)


def saveConfig():
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)


def askUpdateWindow(game, new):
    if args.update:
        return 0
    elif args.no_update:
        return 1
    else:
        txt = f"There is an update available for {game}"
        if new:
            txt = f"There is a NEW update available for {game}"
        layout = [
            [sg.Text(txt)],
            [sg.Button("Skip Update"), sg.Button("Update")],
        ]
        window = sg.Window("NoUpdate Launcher", layout)
        while True:
            event, values = window.read()
            window.close()
            # See if user wants to quit or window was closed
            if event == sg.WINDOW_CLOSED:
                return -1
            elif event == "Update":
                return 0
            else:
                return 1


def selectMode():
    layout = [
        [sg.Text(f"Select the behavior for this game when an update is available")],
        [
            sg.Button("Ask at each startup", key="ask_start"),
            sg.Button("Ask for each new version", key="ask_version"),
            sg.Button("Never ask", key="never"),
        ],
    ]
    window = sg.Window("NoUpdate Launcher", layout)
    while True:
        event, values = window.read()
        window.close()
        if event == sg.WINDOW_CLOSED:
            return -1
        elif event == "ask_start":
            return 0
        elif event == "ask_version":
            return 1
        elif event == "never":
            return 2


def selectBranch(value):
    layout = [
        [sg.Text("Select the depot branch (default: public)")],
        [sg.Input(value, key="branch")],
        [sg.Button("OK"), sg.Button("Cancel")],
    ]
    window = sg.Window("NoUpdate Launcher", layout)

    while True:
        event, values = window.read()
        window.close()
        if event == sg.WINDOW_CLOSED or event == "Cancel" or values["branch"] == "":
            return -1
        return values["branch"]


def askRestartSteam():
    if args.no_steam:
        return
    elif args.steam:
        restartSteam()
    else:
        layout = [
            [sg.Text("To apply these changes, we need to restart steam. Continue ?")],
            [sg.Button("YES"), sg.Button("NO")],
        ]
        window = sg.Window("NoUpdate Launcher", layout)

        while True:
            event, values = window.read()
            window.close()
            if event == "YES":
                restartSteam()
            return


parser = argparse.ArgumentParser()
parser.add_argument("-a", "--appid", type=str, help="the app id", required=False)
parser.add_argument(
    "-y",
    "--update",
    action="store_true",
    help="allow update if available",
    required=False,
    default=False,
)
parser.add_argument(
    "-n",
    "--no-update",
    action="store_true",
    help="block update if available",
    required=False,
    default=False,
)
parser.add_argument(
    "-s",
    "--steam",
    action="store_true",
    help="skip steam prompt and allow restart",
    required=False,
    default=False,
)
parser.add_argument(
    "-ns",
    "--no-steam",
    action="store_true",
    help="skip steam prompt and deny restart",
    required=False,
    default=False,
)
args = parser.parse_args()

print(
    "    _   __      __  __          __      __          __                           __             \n"
    "   / | / /___  / / / /___  ____/ /___ _/ /____     / /   ____ ___  ______  _____/ /_  ___  _____\n"
    "  /  |/ / __ \/ / / / __ \/ __  / __ `/ __/ _ \   / /   / __ `/ / / / __ \/ ___/ __ \/ _ \/ ___/\n"
    " / /|  / /_/ / /_/ / /_/ / /_/ / /_/ / /_/  __/  / /___/ /_/ / /_/ / / / / /__/ / / /  __/ /    \n"
    "/_/ |_/\____/\____/ .___/\__,_/\__,_/\__/\___/  /_____/\__,_/\__,_/_/ /_/\___/_/ /_/\___/_/     \n"
    "                 /_/                                                                            \n"
)

if args.appid is not None:
    run(args.appid)
else:
    mainWindow()
