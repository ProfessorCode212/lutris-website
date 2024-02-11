import os
import git
import logging

# import yaml
import requests
from django.conf import settings
from providers.models import ProviderGame

LOGGER = logging.getLogger(__name__)

PROTONFIXES_URL = "https://github.com/Open-Wine-Components/ULWGL-protonfixes"
ULWGL_API_URL = "https://ulwgl.openwinecomponents.org/ulwgl_api.php"
PROTONFIXES_PATH = os.path.join(settings.MEDIA_ROOT, "protonfixes")
PROTON_PATCHES_STEAM_IDS = os.path.join(settings.MEDIA_ROOT, "proton-steamids.txt")


def update_repository():
    if os.path.exists(PROTONFIXES_PATH):
        repo = git.Repo(PROTONFIXES_PATH)
        remote = git.remote.Remote(repo, "origin")
        remote.pull()
    else:
        repo = git.Repo.clone_from(PROTONFIXES_URL, PROTONFIXES_PATH)


def get_ulwgl_api_games():
    response = requests.get(ULWGL_API_URL)
    games_by_id = {}
    for entry in response.json():
        appid = entry["ulwgl_id"]
        if appid in games_by_id:
            games_by_id[appid].append(entry)
        else:
            games_by_id[appid] = [entry]
    return games_by_id


def get_game_ids(gamefix_folder):
    fixes = os.listdir(os.path.join(PROTONFIXES_PATH, gamefix_folder))
    game_ids = []
    for fix in fixes:
        base, ext = os.path.splitext(fix)
        if ext != ".py":
            continue
        if base in ("__init__", "default", "winetricks-gui"):
            continue
        if base.startswith("ulwgl-"):
            base = base.split("ulwgl-")[1]
        game_ids.append(base)
    return game_ids


def get_all_fixes_ids():
    game_ids = set()
    for folder in iter_gamefix_folders():
        for game_id in get_game_ids(folder):
            game_ids.add(game_id)
    with open(PROTON_PATCHES_STEAM_IDS) as patch_ids_file:
        for line in patch_ids_file.readlines():
            appid = line.strip()
            game_ids.add(appid)
    return game_ids


def check_lutris_associations():
    ulwgl_games = get_ulwgl_api_games()
    fixes_ids = get_all_fixes_ids()
    seen_fixes = set()
    for game_id in ulwgl_games:
        steam_id = None
        for store_game in ulwgl_games[game_id]:
            if steam_id:
                continue
            steam_id = store_game["ulwgl_id"].split("ulwgl-")[1]
            if steam_id not in fixes_ids:
                LOGGER.warning("%s (%s) has no fixes", store_game["title"], steam_id)
            else:
                seen_fixes.add(steam_id)
            if not steam_id.isnumeric() or steam_id == store_game["codename"]:
                LOGGER.info(
                    "Non Steam game %s with id %s", store_game["title"], steam_id
                )
                steam_id = None

            if steam_id:
                try:
                    steam_provider_game = ProviderGame.objects.get(
                        provider__name="steam", slug=steam_id
                    )
                except ProviderGame.DoesNotExist:
                    LOGGER.warning("Steam game with ID %s not found")
                    continue

                log_lutris_games(steam_provider_game, "In API")
                # lutris_game = lutris_games[0]
                # LOGGER.info(
                #     "Steam game %s (%s) with id %s",
                #     steam_provider_game.name,
                #     lutris_game.name,
                #     steam_provider_game.internal_id,
                # )
    steam_games_not_found = set()
    provider_games = []
    for game_id in fixes_ids - seen_fixes:
        try:
            steam_provider_game = ProviderGame.objects.get(
                    provider__name="steam", slug=game_id
            )
        except ProviderGame.DoesNotExist:
            steam_games_not_found.add(game_id)
            steam_provider_game = None
        if steam_provider_game:
            provider_games += log_lutris_games(steam_provider_game, "Fix not in DB")
    for (provider_game, steam_game) in provider_games:
        print(f"{provider_game.name},{provider_game.provider.name},{provider_game.slug},ulwgl-{steam_game.slug},,")
    if steam_games_not_found:
        LOGGER.warning(steam_games_not_found)


def log_lutris_games(steam_provider_game, context=""):
    lutris_games = steam_provider_game.games.all()
    if not lutris_games:
        LOGGER.warning(
            "No associated Lutris game for %s", steam_provider_game
        )
        return []
    if lutris_games.count() > 1:
        LOGGER.warning(
            "More than one Lutris game for %s", steam_provider_game
        )
        for lutris_game in lutris_games:
            LOGGER.warning(lutris_game)
    lutris_game = lutris_games[0]
    provider_games = []
    for provider_game in lutris_game.provider_games.exclude(provider__name__in=("igdb", "steam")):
        LOGGER.info("%s %s", context, provider_game)
        provider_games.append((provider_game, steam_provider_game))
    return provider_games


def print_lutris_matches():
    steam_ids = get_game_ids("gamefixes-steam")
    steam_games = ProviderGame.objects.filter(
        provider__name="steam", appids__in=steam_ids
    )
    for game in steam_games:
        print(
            game["name"],
            ", ".join(
                [f"{prov['service']}:{prov['slug']}" for prov in game["provider_games"]]
            ),
        )
    matched_steam_ids = [
        [p["slug"] for p in g["provider_games"] if p["service"] == "steam"][0]
        for g in steam_games
    ]
    print("Unmatched IDs")
    print(set(steam_ids) - set(matched_steam_ids))


def parse_python_fix(file_path):
    with open(file_path, "r", encoding="utf-8") as python_script:
        script_content = python_script.readlines()
    fixes = []
    fixes_started = False
    complex_script = False
    for line in script_content:
        if line.startswith("def main"):
            fixes_started = True
            continue
        if not fixes_started:
            continue
        if line.strip().startswith(('"""', "#")) or not line.strip():
            continue
        if line.strip().startswith("util"):
            line = line.strip().replace("util.", "")
            if line.startswith(
                ("winedll_override", "set_environment", "replace_command")
            ):
                line = line.replace("', '", "=").replace("','", "=")
            if not line.startswith(("regedit_add", "append_arguments")):
                line = line.replace("('", ": ").replace("()", "")
            if not line.startswith(("set_ini_options")):
                line = line.replace("')", "")
            fixes.append(line.strip())
        else:
            complex_script = True
    if complex_script:
        fixes.append("additional_fixes")
    return fixes


def iter_gamefix_folders():
    for path in os.listdir(os.path.join(PROTONFIXES_PATH)):
        if not path.startswith("gamefixes-"):
            continue
        yield path


def parse_protonfixes(gamefix_folder):
    fixes = {}
    store_path = os.path.join(PROTONFIXES_PATH, gamefix_folder)
    fix_files = os.listdir(store_path)
    for fix in fix_files:
        appid, ext = os.path.splitext(fix)
        if appid in ("default", "__init__"):
            continue
        fixes[appid] = parse_python_fix(os.path.join(store_path, fix))
    return fixes


def convert_to_lutris_script(protonfix):
    ignored_tasks = (
        "disable_protonaudioconverter",
        "additional_fixes",
        "use_seccomp",
        "_mk_syswow64",
        "create_dosbox_conf",
        "set_cpu_topology_nosmt",
        "set_xml_options",
        "disable_uplay_overlay",
        "disable_nvapi",
    )
    installer = {"game": {}, "installer": [], "wine": {}, "system": {}}
    script = []
    for task in protonfix:
        if task.startswith("protontricks"):
            verb = task.split(": ")[1]
            script.append({"task": {"name": "winetricks", "app": verb}})
            continue
        if task.startswith(ignored_tasks):
            # Ignore, only applicable to Proton
            continue
        if task.startswith("append_argument"):
            installer["game"]["args"] = task.split(": ")[1]
            continue
        if task.startswith("winedll_override"):
            if "overrides" not in installer["wine"]:
                installer["wine"]["overrides"] = {}
            key, value = task.split(": ")[1].split("=", maxsplit=1)
            installer["wine"]["overrides"][key] = value
            continue
        if task.startswith(("set_ini_options", "regedit_add")):
            # TODO
            continue
        if task.startswith("set_environment"):
            if "env" not in installer["system"]:
                installer["system"]["env"] = {}
            key, value = task.split(": ")[1].split("=", maxsplit=1)
            installer["system"]["env"][key] = value
            continue
        if task.startswith("replace_command"):
            installer["game"]["exe"] = task.split(": ")[1]
            continue
        if task.startswith("install_eac_runtime"):
            installer["wine"]["eac"] = True
            continue
        if task.startswith("install_battleye_runtime"):
            installer["wine"]["battleye"] = True
            continue
        if task.startswith("disable_esync"):
            installer["wine"]["esync"] = False
            continue
        if task.startswith("disable_fsync"):
            installer["wine"]["fsync"] = False
            continue
        if task.startswith("set_cpu_topology_limit"):
            installer["system"]["single_cpu"] = True
            installer["system"]["limit_cpu_count"] = task.split("(")[1].rstrip(")")
            continue
        raise ValueError("unhandled task: %s in %s" % (task, protonfix))
    installer["installer"] = script
    return {k: v for k, v in installer.items() if v}


if __name__ == "__main__":
    update_repository()
    print_lutris_matches()
    # results = parse_protonfixes()
    # print(json.dumps(results, indent=2))
    # for key, fix in results.items():
    #     res = convert_to_lutris_script(fix)
    #     if res:
    #         print(key)
    #         print(yaml.dump(res))