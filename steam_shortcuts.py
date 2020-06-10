import sys, winreg, pathlib, re, urllib3, shutil, traceback, json
from io import StringIO
from PIL import Image
from os import path

STEAM_API = "http://api.steampowered.com/"
KEY = "66D1275E24E6B963247C47EF178BD6B1"

http = urllib3.PoolManager()


def main():
    """
    Where the magic happens
    """

    # Get path to Steam and libraries
    steam_path, library_index_path = get_steam_library_index()
    libraries = get_library_folders(steam_path, library_index_path)

    if not libraries:
        print("No libraries to check")
        exit(0)

    icons = get_steam_game_icons()

    # Show game and folder info to user
    games = get_installed_games(libraries, icons)
    print(
        f"Found {len(games)} game{'s' if len(games) > 1 else ''} in the following libraries:"
    )
    print("\n".join(map(lambda x: f"  {x}", libraries)))

    # Try and find any existing icons for the found games
    check_for_icons(games)
    found_icons = len([True for game in games.values() if game["icon"]])
    print(f"\nFound {found_icons} icon{'s' if found_icons != 1 else ''}")
    # Ask the user if they'd like to download the missing icons
    # By default will download missing icons and create shortcuts with missing icons
    create_with_missing, try_download, start_menu = True, True, False
    missing = len(games) - found_icons
    if missing > 0:
        print(f"\nNeed to acquire {missing} icon{'s' if missing != 1 else ''}")
        try_download = input("Try to download them now? [Y]/n ").lower().strip() != "n"

    if try_download:
        get_icons(games)

    # Check for any icons that are still missing
    failed = [game["name"] for game in games.values() if not game["icon"]]
    if failed and try_download:
        print(
            f"\nFailed to acquire the following {len(failed)} icon{'s' if len(failed) != 1 else ''}"
        )
        print("\n".join(map(lambda x: f"  {x}", failed)))

    # Ask if the user would like to create shortcuts with missing icons
    create_with_missing = (
        input("\nCreate shortcuts for games without icons? [Y]/n ").lower().strip()
        != "n"
    )

    start_menu = (
        input("\nAdd shortcuts to a Start Menu folder (requires Admin)? y/[N] ")
        .lower()
        .strip()
        == "y"
    )

    # Create shortcuts, show some stats, and exit
    try:
        count, folder = create_shortcuts(games, create_with_missing, start_menu)
    except PermissionError:
        print(
            "\n\nTo add to the start menu, please run this tool from an elevated (admin) terminal"
        )
        print("Falling back to ./shortcuts")
        count, folder = create_shortcuts(games, create_with_missing)

    print(f"\nDone! Created {count} shortcut{'s' if count != 1 else ''}")
    print(
        f"You can find them in {f'./{folder}' if not start_menu else f'your Start Menu ({folder})'}"
    )


"GetOwnedGames"


def get_steam_game_icons():
    username = input("Please enter your Steam username (not nickname): ")
    id_endpoint = (
        f"{STEAM_API}ISteamUser/ResolveVanityURL/v0001/?key={KEY}&vanityurl={username}"
    )
    resolve_id = http.request("GET", id_endpoint)
    body = json.loads(resolve_id.data.decode("utf-8"))
    id = None
    if body["response"]["success"] == 1:
        id = body["response"]["steamid"]

    if id is None:
        print(
            "Could not retrieve SteamID from username. Double check your username and try again"
        )
        print("If this issue persists, please report it on github!")
        exit(-1)

    games_endpoint = f"{STEAM_API}IPlayerService/GetOwnedGames/v0001/?key={KEY}&steamid={id}&format=json&include_appinfo=true&include_played_free_games=true"
    resolve_id = http.request("GET", games_endpoint)
    body = json.loads(resolve_id.data.decode("utf-8"))
    if len(body["response"]) == 0:
        print(f"Empty response from SteamAPI for user {username} ({id})")
        with open("error_log.txt", "a", encoding="utf-8") as f:
            f.write(f"Empty response from SteamAPI for user {username} ({id}):\n")
            f.write(json.dumps(body))

        exit(-1)

    appid_to_icon = {
        str(game["appid"]): f"{game['img_icon_url']}.jpg"
        for game in body["response"]["games"]
    }

    return appid_to_icon


def get_steam_library_index():
    """
    Tries to get the Steam installation folder, or asks the user. 
    This will also get the location to the library listings file, 
    which forms part of the check to make sure it's the right folder.

    Returns a tuple of (steam_path, library_index_path)
    """

    # Search Registry
    try:
        hkey = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\WOW6432Node\Valve\Steam"
        )
    except:
        hkey = None
        print(sys.exc_info())
    try:
        steam_path = winreg.QueryValueEx(hkey, "InstallPath")[0]
    except:
        steam_path = None
        print(sys.exc_info())
    winreg.CloseKey(hkey)

    # Ask the user if the registry was unhelpful
    if not steam_path:
        steam_path = input(
            "Failed to find Steam installation path, please provide the path e.g. C:\Program Files (x86)\Steam, ~/.local/steam, etc\n"
        )

    steam_path = pathlib.Path(steam_path)

    # Try and get the library index file as a sanity check for the right folder
    try:
        library_index_path = pathlib.Path(
            [x for x in steam_path.glob("steamapps/libraryfolders.vdf")][0]
        )
    except:
        print("This doesn't look like the right folder!")
        exit()

    return (steam_path, library_index_path)


def get_library_folders(steam_path, library_index_path):
    """
    Reads the library index file `libraryfolders.vdf` to get a list of all
    Steam library locations on your system.
    
    Because of the lazy way in which the RegEx is written, it only supports
    up to 100 Steam libraries... but come on.

    Returns the library locations
    """

    locations = []

    # Find the lines matching a library folder (the library index, and the location)
    p = re.compile('"\d{1,3}".+".+"')
    with open(library_index_path.resolve(), encoding="utf-8") as index:
        locations = [p.findall(line.strip()) for line in index if p.search(line)]

    libraries = [
        pathlib.Path(l[0].split("\t\t")[1].replace('"', "")) for l in locations
    ]
    libraries.append(steam_path)

    return sorted(libraries)


def get_installed_games(libraries, icons):
    """
    For each library, parse all the appmanifest_xxx.acf files for
    game names and install locations, where xxx is the appid of an installed game.

    Returns a dictionary of appid -> {name, location, icon} 
    """

    # Horrible flattening of each manifest file
    manifests = [
        item
        for sublist in [
            [x for x in path.glob("steamapps/appmanifest_*.acf")] for path in libraries
        ]
        for item in sublist
    ]

    # We want to find the game name and install directory
    patterns = [re.compile('"name".+".+"'), re.compile('"installdir".+".+"')]
    games = dict()

    # Parse each manifest and build the games dict
    for m in manifests:
        try:
            with open(m.resolve(), encoding="utf-8") as acf:
                lines = acf.readlines()
                name, location = [
                    p.search("\n".join([l.strip() for l in lines])) for p in patterns
                ]

                if name and location:
                    appid = m.stem.split("_")[1]
                    name, location = [
                        field[0].replace('"', "").split("\t\t")[1]
                        for field in [name, location]
                    ]
                    location = m.parent / f"common/{location}"
                    try:
                        location.resolve(strict=True)
                    except:
                        continue
                    games[appid] = {
                        "name": name,
                        "location": location,
                        "icon": None,
                        "icon_hash": icons[appid].split(".")[0]
                        if appid in icons.keys()
                        else None,
                        "icon_ext": icons[appid].split(".")[1]
                        if appid in icons.keys()
                        else None,
                    }
                else:
                    print(
                        f"  Couldn't locate name or location for file {m}\n  Name: {name}\n  Location: {location}\n"
                    )

        except KeyboardInterrupt as e:
            raise
        except Exception as e:
            print("Unhandled exception when reading file", m, e)

    return games


def check_for_icons(games):
    """
    For each game, checks to see if an icon exists the  game by looking
    for an icon.ico in the game's installation directory
    """

    for appid, game in games.items():
        try:
            icon_path = pathlib.Path(
                game["location"] / f"{game['icon_hash']}.{game['icon_ext']}"
            )
            games[appid]["icon"] = icon_path.resolve(strict=True)
        except Exception as e:
            continue


def get_icons(games):
    """
    This will attempt to download all missing icons from SteamDB and Steam's CDN
    It might fail, in which case the {appid -> icon} remains None
    """

    for appid, game in filter(lambda g: not g[1]["icon"], games.items()):
        print(f"  Downloading icon for {appid} ({game['name']})")
        try:
            if game["icon_hash"] is None:
                raise Exception(f"No Icon URL found for {appid} ({game['name']})")

            # Write the ico data to an icon file in the game's install dir
            icon_url = f"https://steamcdn-a.akamaihd.net/steamcommunity/public/images/apps/{appid}/{game['icon_hash']}.{game['icon_ext']}"
            icon_path = pathlib.Path(game["location"] / f"{game['icon_hash']}.ico")
            with http.request("GET", icon_url, preload_content=False) as jpg_data, open(
                icon_path, "wb+"
            ) as ico_file:
                jpg = Image.open(jpg_data)
                jpg.save(icon_path)
            jpg_data.release_conn()

            # Set the icon location for the game
            games[appid]["icon"] = icon_path
        except KeyboardInterrupt:
            raise
        except Exception as e:
            with open("error_log.txt", "a", encoding="utf-8") as f:
                f.write(traceback.format_exc())


def create_shortcuts(games, create_with_missing, start_menu=False):
    """
    For each game, now create the URL shortcuts to steam://rungameid/{appid}, 
    set the icon if it exists, or blank if the user asks for icon-less shortcuts

    Returns the number of shortcuts created
    """

    if start_menu:
        s = pathlib.Path(
            path.expandvars(
                "%SystemDrive%\ProgramData\Microsoft\Windows\Start Menu\Programs"
            )
        )
        folder = s / "Steam Games"
    else:
        folder = pathlib.Path("./shortcuts")
    folder.mkdir(parents=True, exist_ok=True)
    count = 0
    for appid, game in games.items():
        # Sanitise the game's name for use as a filename
        filename = re.sub(r'[\\/*?:"<>|]', "", game["name"]) + ".url"

        # Skip game if missing the icon and the user asked to
        # not create shortcuts with missing icons
        if not game["icon"] and not create_with_missing:
            continue

        # Write the shortcut file
        with open(folder / filename, "w+", encoding="utf-8") as shortcut:
            shortcut.write("[InternetShortcut]\n")
            shortcut.write("IconIndex=0\n")
            shortcut.write(f"URL=steam://rungameid/{appid}\n")
            shortcut.write(f"IconFile={game['icon']}\n")
        count += 1

    return (count, folder)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt as ke:
        print(ke)
    except Exception:
        print("Unexpected exception", traceback.print_exc())
