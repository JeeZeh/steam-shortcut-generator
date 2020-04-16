# Steam Shortcut Generator

> Note: This tool is currently Windows-only. But I might take the time to add Linux/macOS support if requested! 

---

Ever needed to recreate all of your Steam shortcuts? Maybe you forgot to back them up when reinstalling your OS, or just never created them in the first place...

If you have a large library of installed games and you don't want to manually create the shortcut for each one, then this is the tool for you!

[Here's a demo!](https://www.youtube.com/watch?v=eH-ouDx1Y68)

## Usage

> Note: the shortcuts created are .url links, just like the ones Steam creates - this is because I can't tell which .exe is the one that launches the game, plus Steam sometimes likes to give you launch dialogues

1. You need [Python 3.6 or newer](https://www.python.org/downloads/) installed
1. From the command-line, PowerShell or equivialent terminal, run `python steam_shortcuts.py` or equivalent command to run the script with Python3
1. Follow the prompts to create shortcuts with or without icons
1. The shortcuts will be created in `./shortcuts`, relative to wherever the script was run from

## What it does

1. Checks your registry for the Steam install folder
2. Reads `steamapps/libraryfolders.vdf` to find out where all your Steam libraries are located
3. For each library, parse all the `appmanifest_xxx.acf` files for game names and install locations, where xxx is the appid of an installed game
4. For each game, check if an icon already exists in the game's installation folder - the icon is downloaded by this tool, so it won't exist if you haven't run it before
5. For all missing icons, download them if the user requests
6. For each game, now create the URL shortcuts to `steam://rungameid/{appid}`, set the icon if it exists, or blank if the user asks for icon-less shortcuts
7. Done! No tidying up is done since the icons are kept in the game folders for use by each shortcut. I guess things might break if you uninstall the game, but they're just shortcuts :) 

## Warnings
- I'm not using the Steam API nor or any API for SteamDB. It potentially does a LOT of webscraping, so if you get IP-banned from SteamDB, don't blame me.
- It only supports Windows, and does simple checks for sanity like current folder etc. - If you don't follow the usage instructions and it breaks something, don't blame me. (P.S. All it does is write icon files and create shortcuts, but who knows, this is software) 
- Not all icons created may be usable, like Steamworks Redist, Proton, etc.
