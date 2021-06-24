# NoUpdateLauncher

A simple utility to prevent steam from updating some of your games

## How is it working
This work is based on the [appmanifest hack](https://steamcommunity.com/sharedfiles/filedetails/?id=1985923465).<br>
To launch your game, you can open this software or use the shortcut created. Then, when you want to start your game, this software will be launched and will check if there is a new manifest available. If this is the case, it will ask if you want to update or not. If you don't want to update, the software will edit your game's appmanifest and will set the manifest ids to the latest availables. You will then need to restart steam, and the game will start without updating.<br><br>
**Important**: You need to start the game with this software or with a shortcut created by this software to prevent any potential update. Starting it via steam will not work.

## UI
|Button|Description|
|--|--|
|Enable|Enable updates monitoring for this game, this will automatically set your update mode to "update only when launching the game"|
|Disable|Disable update monitoring, this will revert the manifest ids to their values when you enabled the game, the game will likely update afterwards|
|Mode [x]|Set the prompt mode: 0: ask if you want to update each time you launch the game, 1: ask only when a new version is available, 2: never ask and always prevent the game from updating|
|Branch|Change the depot branch (the default is "public", you will not likely need to change this)|
|Create Shortcut|Create a shortcut on your desktop to perform an update check and then launch the game (it may take a few seconds)|
|Play|performs an update check  and launch the game (same function as the shortcut)|
|Check Updates|performs an update check|

## Developement
- To install the required tools, run `pip3 install -r requirements.txt`
- To package the software as an executable, run `pyinstaller -F main.py`
- To perform an update check and start a game, run `noupdatelauncher.exe -a <APPID>`
