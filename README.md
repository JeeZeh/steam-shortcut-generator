# Steam Shortcut Generator

> Note: This tool is currently Windows-only. But I might take the time to add Linux/macOS support if requested! 

> This tool used to use SteamDB to fetch the hi-res .ico file for each game, but scraping was causing some IP-ban issues (sorry). It has been rewritten to use the SteamAPI (in combination with your username) to fetch the icons from the Steam CDN directly. Unfortunately, the quality for each icon is a low-res jpg, as the API does not provide the .ico links - I will investigate this and fix it soon. If successful, I'll be able to remove the Pillow dependency too!

---

**Steam now supports this through selecting multiple library games > Manage > Create Desktop Shortcuts**.
It can't, however, add them to the start menu for you automatically. This tool can!

Ever needed to recreate all of your Steam shortcuts? Maybe you forgot to back them up when reinstalling your OS, or just never created them in the first place...

If you have a large library of installed games and you don't want to manually create the shortcut for each one, then this is the tool for you!

[Here's a demo!](https://www.youtube.com/watch?v=eH-ouDx1Y68)

## Usage

> Note: the shortcuts created are .url links, just like the ones Steam creates - this is because I can't tell which .exe is the one that launches the game, plus Steam sometimes likes to give you launch dialogues

1. You need [Python 3.6 or newer](https://www.python.org/downloads/) installed.
2. Your Steam profile must have game library set to publicly visible.
3. You will need to run `[your python3 alias] -m pip install pillow urllib3 vdf` 
4. From the command-line, PowerShell or equivialent terminal, run `[your python3 alias] steam_shortcuts.py`.
5. Follow the prompts to create shortcuts with or without icons. You'll need to enter your Steam name, this is just used to cross reference the games you own for their icon file.
6. The shortcuts will be created in `./shortcuts`, relative to wherever the script was run from

## What it does

1. Checks your registry for the Steam install folder
2. Reads `steamapps/libraryfolders.vdf` to find out where all your Steam libraries are located
3. For each library, parse all the `appmanifest_xxx.acf` files for game names and install locations, where xxx is the appid of an installed game
4. For each game, check if an icon already exists in the game's installation folder - the icon is downloaded by this tool, so it won't exist if you haven't run it before
5. For all missing icons, download them if the user requests
6. For each game, now create the URL shortcuts to `steam://rungameid/{appid}`, set the icon if it exists, or blank if the user asks for icon-less shortcuts
7. Done! No tidying up is done since the icons are kept in the game folders for use by each shortcut. I guess things might break if you uninstall the game, but they're just shortcuts :) 

## Warnings
- The icons are currently LOW res due to the SteamAPI not providing a high quality link, like scraping SteamDB used to.
- Your Steam account must own the games for the tool to fetch the icons. It can still create icon-less shortcuts if you want though.
- It will try to use your username to retrieve your Steam profile & ID. If you set a custom profile URL you should enter that (the end ID-part) as your username.
- It only supports Windows, and does simple checks for sanity like current folder etc. - if you don't follow the usage instructions (or if you do) and it breaks something, don't blame me. (P.S. All it does is write icon files and create shortcuts, but who knows, this is software) 
- Not all icons created may be usable, like Steamworks Redist, Proton, etc.
