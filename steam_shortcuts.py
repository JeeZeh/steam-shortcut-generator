import json
import pathlib
import re
import sys
import traceback
from typing import List, Tuple, Dict, Any, Optional
import winreg
from os import path
import os
import platform

import urllib3
import vdf
from PIL import Image

STEAM_API = "http://api.steampowered.com/"
KEY = "20F58DAB4E215359D7667DB18C99BD8D"
games_endpoint = f"{STEAM_API}IPlayerService/GetOwnedGames/v0001/?key={KEY}&format=json&include_appinfo=true&include_played_free_games=true&steamid="
id_endpoint = f"{STEAM_API}ISteamUser/ResolveVanityURL/v0001/?key={KEY}&vanityurl="
http = urllib3.PoolManager()


def main():
    """
    Where the magic happens
    """

    # Get path to Steam and libraries
    steam_path = get_steam_path()
    library_path = get_steam_library_path(steam_path)
    libraries = get_library_folders(steam_path, library_path)
    local_users = get_steam_local_user_ids(steam_path)

    if not libraries:
        print("No libraries to check")
        sys.exit(0)

    icons = get_steam_game_icons(local_users)

    # Show game and folder info to user
    games = get_installed_games(libraries, icons)
    print(
        f"Found {len(games)} game{'s' if len(games) > 1 else ''} in the following libraries:"
    )
    print("\n".join(map(lambda x: f"  {x}", libraries)))

    games_without_icon_hashes = [
        "  " + game["name"] for game in games.values() if game["icon_hash"] is None
    ]

    if games_without_icon_hashes:
        print(
            f"\nFound installed games ({len(games_without_icon_hashes)}) which don't belong to your account."
        )
        print("\n".join(games_without_icon_hashes))
        print(
            "Shortcuts for these games can still be created, but they will not have icons."
        )

    # Try and find any existing icons for the found games
    check_for_icons(games)
    found_icons = len([True for game in games.values() if game["icon"]])
    print(f"\nFound {found_icons} existing game icon{'s' if found_icons != 1 else ''}")
    # Ask the user if they'd like to download the missing icons
    # By default will download missing icons and create shortcuts with missing icons
    create_with_missing, try_download, start_menu = True, True, False
    missing = len(games) - found_icons
    if missing > 0:
        print(f"\nMissing icons for {missing} game{'s' if missing != 1 else ''}")
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

    # Add non-Steam games
    add_non_steam_games = (
        input("\nWould you like to add non-Steam games? y/[N] ").lower().strip() == "y"
    )
    if add_non_steam_games:
        non_steam_games = get_non_steam_games()
        games.update(non_steam_games)

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


def get_non_steam_games() -> Dict[str, Dict[str, Any]]:
    """
    Reads non-Steam game details from user input.
    Returns a dictionary of appid -> {name, location, executable, arguments, icon, icon_hash, icon_ext, is_non_steam}
    """
    non_steam_games = {}

    def sanitize_filename(name):
        """Sanitize filename to remove invalid characters"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '_')
        return name

    while True:
        name = input("Enter the name of the non-Steam game (or 'done' to finish): ")
        if name.lower() == "done":
            break

        # Sanitize name for file system
        sanitized_name = sanitize_filename(name)
        if sanitized_name != name:
            print(f"Note: Name will be saved as '{sanitized_name}' for filesystem compatibility")
            name = sanitized_name

        # Get full executable path
        executable_path = input(f"Enter the full path to the executable for {name}: ")

        if not os.path.isfile(executable_path):
            print(f"Warning: Executable file not found at {executable_path}")
            continue_anyway = input("Continue anyway? [Y]/n: ").lower().strip() != "n"
            if not continue_anyway:
                continue

        # Get optional command line arguments
        arguments = input(f"Enter any command line arguments for {name} (optional): ")

        # Split into location directory and executable filename
        location = os.path.dirname(executable_path)
        executable = os.path.basename(executable_path)

        # Get icon path (optional)
        icon_path = input(f"Enter the path to the icon for {name} (optional): ")
        icon = None
        if icon_path:
            if not os.path.isfile(icon_path):
                print(f"Warning: Icon file not found at {icon_path}")
            else:
                # Check if it's a valid icon file
                valid_icon = False
                try:
                    # Try to open with PIL to validate
                    if icon_path.lower().endswith(('.ico', '.exe', '.dll')):
                        # These are valid icon sources
                        valid_icon = True
                    elif icon_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                        # For image files, check if they can be opened
                        Image.open(icon_path)
                        valid_icon = True
                except Exception:
                    valid_icon = False

                if not valid_icon:
                    print(f"Warning: Icon file at {icon_path} is not in a supported format")
                else:
                    icon = icon_path

        # Generate a unique ID for this non-Steam game
        appid = f"nonsteam_{len(non_steam_games) + 1}"

        # Check if a game with this name already exists in our dictionary
        existing_names = [game["name"] for game in non_steam_games.values()]
        if name in existing_names:
            # Append a number to make the name unique
            counter = 1
            while f"{name} ({counter})" in existing_names:
                counter += 1
            name = f"{name} ({counter})"
            print(f"A game with this name already exists. Renamed to: {name}")

        non_steam_games[appid] = {
            "name": name,
            "location": location,
            "executable": executable,
            "arguments": arguments,
            "icon": icon,
            "icon_hash": None,
            "icon_ext": None,
            "is_non_steam": True
        }

    return non_steam_games


def is_integer(x):
    try:
        int(x)
        return True
    except ValueError:
        return False


def get_steam_game_icons(local_users: List[Tuple[str, str]]):
    games_endpoint = f"{STEAM_API}IPlayerService/GetOwnedGames/v0001/?key={KEY}&format=json&include_appinfo=true&include_played_free_games=true&steamid="
    print("This tool needs to know your Steam ID (long number).")

    username, steam_id = determine_username_id(local_users)

    # Verify Steam ID is numeric
    if not steam_id.isdigit():
        print("Error: Steam ID must be numeric.")
        sys.exit(-1)

    headers = {
        'User-Agent': 'steam-shortcut-generator/1.0',
        'Accept': 'application/json'
    }

    try:
        resolve_id = http.request("GET", games_endpoint + steam_id, headers=headers)

        if resolve_id.status == 400:
            print("\nError: Bad Request - Possible causes:")
            print("1. Invalid Steam API key (get a new one from https://steamcommunity.com/dev/apikey)")
            print(f"2. Invalid Steam ID: {steam_id}")
            print(f"3. API URL: {games_endpoint + steam_id}")
            sys.exit(-1)

        if resolve_id.status != 200:
            print(f"Error: Unexpected status code {resolve_id.status} from Steam API.")
            sys.exit(-1)

        try:
            body = json.loads(resolve_id.data.decode("utf-8"))
        except json.JSONDecodeError as e:
            print("Error: Failed to decode Steam API response")
            print(f"Raw response: {resolve_id.data.decode('utf-8', errors='replace')}")
            print(f"JSON decode error: {str(e)}")
            sys.exit(-1)

        if not body.get("response") or not body["response"].get("games"):
            print(f"\nEmpty response from SteamAPI")
            print(f"{steam_id}'s game library is not publicly visible")
            with open("error_log.txt", "a", encoding="utf-8") as f:
                f.write(f"Empty response from SteamAPI for user {username} ({steam_id}):\n")
                f.write(json.dumps(body))
            sys.exit(-1)

        appid_to_icon = {
            str(game["appid"]): f"{game['img_icon_url']}.jpg"
            for game in body["response"]["games"]
            if "img_icon_url" in game and game['img_icon_url']
        }

        return appid_to_icon

    except urllib3.exceptions.HTTPError as e:
        print(f"HTTP Error occurred: {str(e)}")
        sys.exit(-1)


def determine_username_id(local_users: List[Tuple[str, str]]):
    username, steam_id = None, None

    if local_users:
        while True:
            options = "\n".join(
                f"{i+1}) {u[1]} ({u[0]})" for i, u in enumerate(local_users)  # Changed order here
            )
            idx = input(
                "\nFound local users, enter a choice and press Enter:\n"
                + options
                + "\nX) Enter username manually...\nChoice: "
            )
            print()
            if idx.lower() == "x":
                break
            try:
                choice = int(idx)
                if choice > 0 and choice <= len(local_users):
                    steam_id, username = local_users[choice - 1]  # Changed order here
                    break
            except ValueError:
                print("Invalid input: " + idx)

    if username is None or steam_id is None:
        username = input(
            "\nPlease enter your Steam ID, username (not nickname), or custom profile id: "
        )

        steam_id = resolve_steam_id_from_username(username)

        if steam_id is None:
            if is_integer(username):
                print("\nIt looks like you entered an invalid Steam ID")
            else:
                print("\nCould not retrieve SteamID from username: " + username)

            print("Please double check your details and try again.")
            print("If this issue persists, please report it on github!")
            sys.exit(-1)
    return username, steam_id


def resolve_steam_id_from_username(username):
    """
    Tries to resolve ID from username using ResolveVanityURL. On failure, see
    if the username provided was actually an ID already. On failure, return None.
    """

    # Assume username is not an ID
    resolve_id = http.request("GET", id_endpoint + username)
    body = json.loads(resolve_id.data.decode("utf-8"))
    steam_id = None
    if body["response"]["success"] == 1:
        steam_id = body["response"]["steamid"]
        print("Found ID from username: " + steam_id)
        return steam_id
    elif is_integer(username):
        # See if username is an ID
        resolve_id = http.request("GET", games_endpoint + username)
        body = json.loads(resolve_id.data.decode("utf-8"))
        print(resolve_id.status)
        print(len(body["response"]))
        if resolve_id.status == 200 and len(body["response"]) > 0:
            return username

    return None


def get_steam_library_path(steam_path: pathlib.Path) -> pathlib.Path:
    # Try and get the library index file as a sanity check for the right folder
    try:
        return pathlib.Path(
            [x for x in steam_path.glob("steamapps/libraryfolders.vdf")][0]
        )
    except IndexError:
        print("Could not locate local library.")
        sys.exit(-1)


def get_steam_local_user_ids(steam_path: pathlib.Path) -> List[Tuple[str, str]]:
    # Try and get the library index file as a sanity check for the right folder
    users = []
    try:
        login_file = list(steam_path.glob("config/loginusers.vdf"))
        if not login_file:
            return []

        with open(login_file[0]) as index_file:
            lib_vdf = vdf.load(index_file)

            for id_, data in lib_vdf.get("users", {}).items():
                if isinstance(data, dict) and data.get("AccountName"):
                    users.append((id_, data["AccountName"]))

    except Exception:
        print("Could not locate local users.")
    finally:
        return users


def get_steam_path():
    """
    Tries to get the Steam installation folder, or asks the user.
    This will also get the location to the library listings file,
    which forms part of the check to make sure it's the right folder.

    Returns a tuple of (steam_path, library_index_path)
    """

    # Search Registry
    steam_path = None
    hkey = None
    try:
        hkey = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\\WOW6432Node\\Valve\\Steam"
        )
        try:
            steam_path = winreg.QueryValueEx(hkey, "InstallPath")[0]
        except OSError:
            steam_path = None
            print(sys.exc_info())
        finally:
            if hkey:
                winreg.CloseKey(hkey)
    except OSError:
        print(sys.exc_info())

    # Ask the user if the registry was unhelpful
    if not steam_path:
        steam_path = input(
            "Failed to find Steam installation path, please provide the path e.g. C:\\Program Files (x86)\\Steam, ~/.local/steam, etc\n"
        )

    steam_path = pathlib.Path(steam_path)

    return steam_path


def get_library_folders(steam_path, library_index_path):
    """
    Reads the library index file `libraryfolders.vdf` to get a list of all
    Steam library locations on your system.

    Because of the lazy way in which the RegEx is written, it only supports
    up to 100 Steam libraries... but come on.

    Returns the library locations
    """

    libraries = []

    with open(library_index_path) as index_file:
        lib_vdf = vdf.load(index_file)

    for lib in lib_vdf.get("libraryfolders", {}).values():
        if isinstance(lib, dict) and lib.get("path"):
            path = pathlib.Path(lib["path"])
            libraries.append(path)

    libraries.append(steam_path)

    return sorted(libraries)


def get_installed_games(libraries, icons):
    """
    For each library, parse all the appmanifest_xxx.acf files for
    game names and install locations, where xxx is the appid of an installed game.

    Returns a dictionary of appid -> {name, location, icon, icon_hash, icon_ext}
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
                    except FileNotFoundError:
                        continue
                    games[appid] = {
                        "name": name,
                        "location": location,
                        "executable": "",  # Added empty executable field
                        "arguments": "",  # Added empty arguments field
                        "icon": None,
                        "icon_hash": icons[appid].split(".")[0]
                        if appid in icons.keys()
                        else None,
                        "icon_ext": icons[appid].split(".")[1]
                        if appid in icons.keys()
                        else None,
                        "is_non_steam": False  # Added to distinguish from non-Steam games
                    }
                else:
                    print(
                        f"  Couldn't locate name or location for game {m}\n  Name: {name}\n  Location: {location}\n"
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
            icon_path = pathlib.Path(game["location"] / f"{game['icon_hash']}.ico")
            games[appid]["icon"] = icon_path.resolve(strict=True)
        except Exception:
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
        except Exception:
            with open("error_log.txt", "a", encoding="utf-8") as f:
                f.write(traceback.format_exc())


def create_shortcuts(games: Dict[str, Dict[str, Any]],
                    create_with_missing: bool,
                    start_menu: bool = False) -> Tuple[int, str]:
    """
    Creates shortcuts for the given games.
    Returns a tuple of (number of shortcuts created, folder name)
    """
    count = 0
    folder = "shortcuts"

    if start_menu:
        if platform.system() == "Windows":
            folder = os.path.join(os.environ['APPDATA'], "Microsoft", "Windows", "Start Menu", "Programs", "Steam Shortcuts")
        else:
            folder = os.path.join(os.path.expanduser("~"), ".local", "share", "applications", "Steam Shortcuts")

    folder_path = pathlib.Path(folder)
    folder_path.mkdir(parents=True, exist_ok=True)

    # Fix: Add type checking and error handling for game entries
    for appid, game in games.items():
        if not isinstance(game, dict):
            print(f"Skipping invalid game entry: {appid}")
            continue

        if not game.get("icon") and not create_with_missing:
            continue

        try:
            game_name = game.get("name", "Unknown Game")
            # Fix: Replace all filesystem-illegal characters with underscores
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', game_name)
            game_url = f"steam://rungameid/{appid}"

            shortcut_path = folder_path / f"{safe_name}.url"

            # Fix: Add proper URL format and error handling
            with open(shortcut_path, "w", encoding="utf-8") as shortcut:
                shortcut.write("[InternetShortcut]\n")
                shortcut.write(f"URL={game_url}\n")

                if game.get("icon"):
                    icon_path = pathlib.Path(game["icon"]).as_uri()
                    shortcut.write(f"IconFile={icon_path}\n")
                    shortcut.write(f"IconIndex=0\n")

            count += 1

        except Exception as e:
            print(f"Failed to create Windows shortcut for {game.get('name', 'Unknown Game')}: {str(e)}")
            with open("error_log.txt", "a", encoding="utf-8") as f:
                f.write(f"Failed to create shortcut for {appid}: {str(e)}\n")

    return count, folder


def create_windows_shortcut(shortcut_path: pathlib.Path, game: Dict[str, Any], appid: str):
    """
    Creates a Windows shortcut (.lnk) for the given game.
    """
    import pythoncom
    from win32com.shell import shell

    try:
        # Create the shortcut
        shortcut = pythoncom.CoCreateInstance(
            shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink
        )

        # Set target path based on game type
        if game.get("is_non_steam", False):
            # For non-Steam games, create the full path
            target_path = os.path.join(game["location"], game["executable"])
            shortcut.SetPath(target_path)
            shortcut.SetWorkingDirectory(game["location"])

            # Add command line arguments if specified
            if game.get("arguments"):
                shortcut.SetArguments(game["arguments"])
        else:
            shortcut.SetPath(f"steam://rungameid/{appid}")

        # Set icon if available
        if game["icon"]:
            shortcut.SetIconLocation(game["icon"], 0)

        # Save shortcut
        persist_file = shortcut.QueryInterface(pythoncom.IID_IPersistFile)
        persist_file.Save(str(shortcut_path), 0)

    except Exception as e:
        print(f"Failed to create Windows shortcut for {game['name']}: {str(e)}")


def create_linux_shortcut(shortcut_path: pathlib.Path, game: Dict[str, Any], appid: str):
    """
    Creates a Linux shortcut (.desktop) for the given game.
    """
    try:
        # Create the .desktop file content
        if game.get("is_non_steam", False):
            # For non-Steam games, create the full path
            target_path = os.path.join(game["location"], game["executable"])
            exec_command = f'"{target_path}" {game.get("arguments", "")}'
        else:
            exec_command = f'steam://rungameid/{appid}'

        icon_path = game["icon"] if game["icon"] else ""

        desktop_entry = f"""
        [Desktop Entry]
        Version=1.0
        Name={game['name']}
        Exec={exec_command}
        Icon={icon_path}
        Terminal=false
        Type=Application
        Categories=Game;
        """

        # Write the .desktop file
        with open(shortcut_path, 'w') as f:
            f.write(desktop_entry.strip())

        # Make the .desktop file executable
        os.chmod(shortcut_path, 0o755)

    except Exception as e:
        print(f"Failed to create Linux shortcut for {game['name']}: {str(e)}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt as ke:
        print(ke)
    except Exception:
        print("Unexpected exception")
        traceback.print_exc()
