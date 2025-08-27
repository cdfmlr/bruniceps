#!/usr/bin/env python3
"""
bruniceps is a tool for managing tv series and other media resources.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import warnings
# from collections import OrderedDict  # in Python 3.7+ plain dict already preserves insertion order
from copy import deepcopy
from dataclasses import dataclass, asdict
from functools import partial
from pathlib import Path, PosixPath, WindowsPath
from typing import List, Optional, Dict

import yaml  # python3 -m pip install pyyaml
from yaml.representer import BaseRepresenter

DEFAULT_CONFIG_FILE = 'bruniceps.yaml'
DEFAULT_ARIA2C_CMD = "aria2c"
DEFAULT_FFMPEG_CMD = "ffmpeg"
DEFAULT_FFPROBE_CMD = "ffprobe"
DEFAULT_TMP_DIR = Path(tempfile.gettempdir()) / "bruniceps"
DEFAULT_ENCODING_PROFILES = {
    "default": "-map 0 -c:v libsvtav1 -crf 32 -c:a aac -ac 2 -c:s copy",  # av1
    "original": None
}
CONFIG_ENV_VAR = "BRUNICEPS_CONFIG"
# splitter to multiple config files
CONFIG_PATH_SPLITTER = ","

print = partial(print, flush=True)
Path.__repr__ = lambda self: str(self)  # PosixPath('/path') -> '/path', yes im breaking it. sue me.
run = partial(subprocess.run, check=True, stderr=subprocess.STDOUT)


@dataclass
class Episode:
    key: str
    source: str
    encoding: str = 'default'
    format: Optional[str] = None
    dir: Optional[Path] = None  # episode.dir overrides series.dir and the default {catalog.dir}/{series.title}


@dataclass
class Series:
    key: str
    title: str
    catalog: str
    dir: Optional[Path]  # series.dir overrides the default {catalog.dir}/{series.title}
    episodes: List[Episode]


@dataclass
class Catalog:
    key: str
    dir: Path


@dataclass
class MetaConfig:
    tmp_dir: Path
    aria2c_cmd: str
    ffmpeg_cmd: str
    ffprobe_cmd: str
    encoding_profiles: Dict[str, Optional[str]]
    catalogs: Dict[str, Catalog]


@dataclass
class Config:
    meta: MetaConfig
    series: List[Series]
    _from_config_files: Optional[List[Path]] = None  # fill by load_config, for debug only.


def parse_config(raw: Dict) -> Config:
    meta_raw = raw.get('meta', {})
    catalogs_raw = meta_raw.get('catalogs', {})
    catalogs = {
        k: Catalog(key=k, dir=Path(v['dir']))
        for k, v in catalogs_raw.items()
    }

    encoding_profiles = DEFAULT_ENCODING_PROFILES.copy()
    for item in meta_raw.get('encoding_profiles', []):
        encoding_profiles.update(item)

    tmp_dir = Path(meta_raw.get('tmp_dir') or DEFAULT_TMP_DIR)

    meta = MetaConfig(
        tmp_dir=tmp_dir,
        aria2c_cmd=meta_raw.get('aria2c_cmd', DEFAULT_ARIA2C_CMD),
        ffmpeg_cmd=meta_raw.get('ffmpeg_cmd', DEFAULT_FFMPEG_CMD),
        ffprobe_cmd=meta_raw.get('ffprobe_cmd', DEFAULT_FFPROBE_CMD),
        encoding_profiles=encoding_profiles,
        catalogs=catalogs
    )

    series_list = []
    for key, val in raw.get('series', {}).items():
        episodes_raw = val.get('episodes') or []

        series_dir = val.get('dir', None)
        if series_dir is not None:
            series_dir = Path(series_dir)

        episodes = [Episode(**ep) for ep in episodes_raw]

        def ensure_episode_dir(ep: Episode) -> Episode:
            if ep.dir is not None:
                ep.dir = Path(ep.dir)
            return ep

        episodes = list(map(ensure_episode_dir, episodes))

        series_list.append(Series(
            key=key,
            title=val['title'],
            catalog=val['catalog'],
            dir=series_dir,
            episodes=episodes))

    _from_config_files = raw.get('_from_config_files', None)
    return Config(meta=meta, series=series_list, _from_config_files=_from_config_files)


def load_config(paths: str) -> Config:
    """
    load_config read YAML files in paths.

    Multiple config supported by paths str split by comma, files will be merged
    in the order (latter is prior).

    Dirs are recursively walked: all existing YAML files in them will be
    treated as config files, sorted in alphabetical order.

    :arg paths: a str of "path/to/config-file-0.yaml,path/to/config-file-1.yaml,..."
    """
    # config_paths may be files or dirs
    config_paths: List[str] = paths.split(CONFIG_PATH_SPLITTER)

    # config_files are files:
    # all yaml files in dirs will be found out and included there.
    config_files: List[Path] = []

    for config_path in config_paths:
        if not config_path:  # tolerant towards tailing "," and consecutive ",,"
            continue

        config_path = Path(config_path.strip())

        if not config_path.exists():
            raise FileNotFoundError(config_path)

        if config_path.is_file():
            config_files.append(config_path)
        elif config_path.is_dir():
            # order: 01, 1, 11, 2, 3, 31, 8, 9, 99
            config_files.extend(sorted(config_path.rglob("*.yaml")))
        else:
            warnings.warn(f"{config_path=} is neither a file nor a directory. "
                          "Assuming it is a file (may cause trouble).")
            config_files.append(config_path)

    raw = {}  # config in a dict
    for config_file in config_files:
        with open(config_file, 'r') as f:
            part = yaml.safe_load(f)
            _deep_merge_dict(part, raw)

    raw["_from_config_files"] = config_files  # for debug only

    return parse_config(raw)


def _deep_merge_dict(source: Dict, destination: Dict) -> Dict:
    """
    Deep merge two dictionaries: source into destination.
    For conflicts, prefer source's non-zero values over destination's.
    (By non-zero, we mean that bool(value) is True.)

    Stolen from https://github.com/apache/libcloud/blob/c899034cf3a8f719eb27a0a8027b5ffe191135ef/libcloud/compute/drivers/kubevirt.py#L2020

    Example::

        >>> a = {"domain": {"devices": 0}, "volumes": [1, 2, 3], "network": {}}
        >>> b = {"domain": {"machine": "non-exist-in-a", "devices": 1024}, "volumes": [4, 5, 6]}
        >>> _deep_merge_dict(a, b)
        {'domain': {'machine': 'non-exist-in-a', 'devices': 1024}, 'volumes': [1, 2, 3], 'network': {}}

    In the above example:

    - network: exists in source (a) but not in destination (b): add source (a)'s
    - volumes: exists in both, both are non-zero: prefer source (a)'s
    - devices: exists in both: source (a) is zero, destination (b) is non-zero: keep destination (b)'s
    - machine: exists in destination (b) but not in source (a): reserve destination (b)'s

    :param source: RO: A dict to be merged into another.
                   Do not use circular dict (e.g. d = {}; d['d'] = d) as source,
                   otherwise a RecursionError will be raised.
    :param destination: RW: A dict to be merged into. (the value will be modified).

    :return: dict: Updated destination.
    """

    for key, value in source.items():
        if isinstance(value, dict):  # recurse for dicts
            node = destination.setdefault(key, {})  # get node or create one
            _deep_merge_dict(value, node)
        elif key not in destination:  # not existing in destination: add it
            destination[key] = value
        elif value:  # existing: update if source's value is non-zero
            destination[key] = value

    return destination


def spprint_config(config: Config) -> str:
    config = deepcopy(config)

    # ellipsis the episodes source url: "|<-64->|..."
    # commonly they are shown as `    source: ---URL---`, so 64 makes cols = 12+63+3 < 80.
    for series in config.series:
        for episode in series.episodes:
            s = episode.source
            episode.source = s[:64] + (s[64:] and '...')

    # covert to dict
    config = asdict(config)

    # fix cannot represent an object PosixPath
    class AnyRepresenter(BaseRepresenter):
        def represent_any_as_str(self, data):
            return self.represent_scalar('tag:yaml.org,2002:str', str(data))

    try:
        for p in [Path, PosixPath, WindowsPath]:
            yaml.SafeDumper.add_representer(p, AnyRepresenter.represent_any_as_str)
    except:
        pass

    # covert to YAML str
    try:
        config_str = yaml.safe_dump(config, sort_keys=False)
    except yaml.error.YAMLError as exc:
        # fallback: print it anyway
        config_str = f"error: {exc}\nconfig: {config}\n"

    return "\n".join([
        "### BEGIN BRUNICEPS CONFIG ###\n",
        config_str,
        "### END BRUNICEPS CONFIG ###",
    ])


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def file_exists_with_basename(directory: Path, base_name: str) -> bool:
    return any(f.stem == base_name for f in directory.iterdir() if f.is_file())


def download_source(source_url, output_dir: Path, aria2c_cmd: str) -> Path:
    run(aria2c_cmd.split() + [
        '--dir=' + str(output_dir),
        '--auto-file-renaming=false',
        '--allow-overwrite=true',
        '--check-integrity=true',
        # '--summary-interval=0',
        # '--show-console-readout=false',
        source_url
    ])

    files = list(output_dir.iterdir())
    if not files:
        raise FileNotFoundError("No files downloaded")

    latest_file = max(files, key=lambda f: f.stat().st_mtime)
    return latest_file


def encode_video(input_path: Path, output_path: Path, encoding_args: Optional[str], ffmpeg_cmd: str):
    if not encoding_args:
        shutil.copy(input_path, output_path)
    else:
        # `ffmpeg -nostdin` or `ffmpeg ... < /dev/null` is required to run in bg
        # See also:
        # - https://stackoverflow.com/questions/16523746/ffmpeg-hangs-when-run-in-background
        # - https://ffmpeg.org/ffmpeg-all.html#Main-options (search stdin and nostdin on the page)
        run(ffmpeg_cmd.split() + ['-i', str(input_path)] +
            encoding_args.split() + [str(output_path)],
            stdin=subprocess.DEVNULL)


# verify_* methods are asserts: returns None silently if validation passed, otherwise raise a ValueError.

def verify_video(video: Path, ffprobe_cmd: str) -> None:
    """
    Verify that a video file is a valid container.

    :param video: video file path
    :param ffprobe_cmd: ffprobe command or executable path
    :return: silent None if valid, raises ValueError if not
    :raises ValueError: video verification failed
    """
    try:
        run(ffprobe_cmd.split() + [
            "-v", "error",
            "-show_format",
            "-show_streams",
            "-of", "json",
            str(video)])
    # except subprocess.CalledProcessError:
    #     return False
    except Exception as e:
        # print("[verify_video] failed with unexpected error:", e)
        # return False
        raise ValueError(f"Error verifying '{video}': {e}")


def get_video_duration(video: Path, ffprobe_cmd: str) -> float:
    """
    get video duration from ffprobe.

    :param video: video file path
    :param ffprobe_cmd: ffprobe command or executable path
    :return: the video duration in seconds as a float.
    :raises: ValueError if duration is missing or ffprobe fails.
    """
    try:
        result = run(
            ffprobe_cmd.split() + [
                "-v", "error",
                "-select_streams", "v:0",  # check first video stream
                "-show_entries", "format=duration",
                # XXX: drop -select_streams and just read duration from format=duration.
                #      This way it works for both audio-only and video files.
                "-of", "json",
                str(video)
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
        return duration
    except Exception as e:
        raise ValueError(f"Failed to get duration for '{video}': {e}")


def verify_encoded_video_duration(src: Path, dst: Path, ffprobe_cmd: str) -> None:
    """
    verify that the encoded video file is valid and integrity.

    :param src: video file before encoding
    :param dst: encoded video file
    :param ffprobe_cmd: ffprobe command or executable path
    :return: None if valid, raises ValueError if not
    :raises ValueError: video verification failed
    """
    src_duration = get_video_duration(src, ffprobe_cmd=ffprobe_cmd)
    dst_duration = get_video_duration(dst, ffprobe_cmd=ffprobe_cmd)
    if abs(src_duration - dst_duration) > max(5.0, 0.02 * src_duration):  # seconds tolerance
        raise ValueError(f"Bad encoded video: Duration mismatch: src={src_duration}s dst={dst_duration}s")


def files_identical(f1: Path, f2: Path) -> bool:
    # 1. Quick check on file size with a reasonable tolerance.
    if abs(f1.stat().st_size - f2.stat().st_size) > (8 * 1024):  # bytes
        return False

    # 2. If sizes are close enough, perform a full hash comparison.
    h1, h2 = hashlib.md5(), hashlib.md5()
    with open(f1, "rb") as a, open(f2, "rb") as b:
        for chunk in iter(lambda: a.read(8192), b""):
            h1.update(chunk)
        for chunk in iter(lambda: b.read(8192), b""):
            h2.update(chunk)
    return h1.digest() == h2.digest()


def verify_copied_file_identical(src: Path, dst: Path) -> None:
    """
    :return: None if src and dst are identical, raises ValueError if not
    :raises ValueError: src and dst are not identical
    """
    if not files_identical(src, dst):
        raise ValueError(f"Copied dst='{dst}' is not identical to src='{src}'")


def clear_task_dir(task_dir: Path):
    try:
        shutil.rmtree(task_dir)
    except Exception as e:
        print(f"Warning: Failed to clean temp dir {task_dir}: {e}")


def process_episode(ep: Episode, series: Series, catalog: Catalog, meta: MetaConfig):
    task_id = f"{series.key}-{ep.key}"

    # 0. Check if already exists. 

    base_filename = f"{series.title} {ep.key}"

    target_dir = Path(catalog.dir) / series.title
    if series.dir:
        target_dir = Path(series.dir)
    if ep.dir:
        target_dir = Path(ep.dir)

    ensure_dir(target_dir)

    if file_exists_with_basename(target_dir, base_filename):
        print(f"[{task_id}] Skipping, target {{{base_filename}}} already exists in '{target_dir}'.")
        return

    # 1. Download it

    task_dir = Path(meta.tmp_dir) / task_id

    downloaded_dir = task_dir / "downloaded"
    ensure_dir(downloaded_dir)

    print(f"[{task_id}] Downloading to '{downloaded_dir}' from '{ep.source}' by ({meta.aria2c_cmd})...")
    downloaded_file = download_source(ep.source, downloaded_dir, meta.aria2c_cmd)

    print(f"[{task_id}] Verifying video file '{downloaded_file}'...")
    verify_video(downloaded_file, ffprobe_cmd=meta.ffprobe_cmd)

    # 2. Encode it

    encoded_dir = task_dir / "encoded"
    ensure_dir(encoded_dir)

    ext = ep.format if ep.format else downloaded_file.suffix.lstrip('.')
    encoded_file = encoded_dir / f"{downloaded_file.stem}_encoded.{ext}"

    encoding_args = meta.encoding_profiles.get(ep.encoding)

    print(f"[{task_id}] Encoding '{downloaded_file}' to '{encoded_file}' by ({meta.ffmpeg_cmd})...")
    encode_video(downloaded_file, encoded_file, encoding_args, meta.ffmpeg_cmd)

    print(f"[{task_id}] Verifying video file '{downloaded_file}'...")
    verify_video(encoded_file, ffprobe_cmd=meta.ffprobe_cmd)

    print(f"[{task_id}] Verifying encoded video file duration: "
          f"dst='{encoded_file}' comparing to src='{downloaded_file}'...")
    verify_encoded_video_duration(downloaded_file, encoded_file, ffprobe_cmd=meta.ffprobe_cmd)

    # 3. Move it to the target

    target_file = target_dir / f"{base_filename}.{ext}"

    print(f"[{task_id}] Moving '{encoded_file}' to '{target_file}'...")
    shutil.copy(str(encoded_file), str(target_file))

    print(f"[{task_id}] Verifying copied file: dst='{target_file}' from src='{encoded_file}'...")
    verify_copied_file_identical(encoded_file, target_file)

    # 4. Clear the tmp dir

    print(f"[{task_id}] Clearing temp task working dir: '{task_dir}'...")
    clear_task_dir(task_dir)

    print(f"[{task_id}] Done: '{target_file}'.")


def sync(config: Config):
    """subcommand sync downloads, encodes and moves episodes/movies
    defined in configuration file into destination directories.
    Skips any media that already exists at the destination.
    """
    errors: Dict[str, str] = {}  # "catalog/series/ep": "error msg"

    for series in config.series:
        catalog = config.meta.catalogs[series.catalog]
        for ep in series.episodes:
            try:
                process_episode(ep, series, catalog, config.meta)
            except Exception as e:
                print(f"[sync] ❌ process episode failed: {catalog.key}/{series.key}/{ep.key}: {e}")
                errors[f"{catalog.key}/{series.key}/{ep.key}"] = f"{type(e).__name__}: {e}"

    if not errors:
        print("[sync] Done. ✅ All episodes succeeded.")
    else:
        print("[sync] Done. ❌ Some episodes failed: \n")
        for key, error in errors.items():
            print(f"   - ⚠️ [{key}]: {error}")


def dry_run(config: Config):
    """subcommand dry-run prints the loaded config and exit."""
    print("[dry-run] Config loaded:\n\n", spprint_config(config), sep="", end="\n\n")
    print("[dry-run] Done.")


def main():
    parser = argparse.ArgumentParser(prog="bruniceps", description=__doc__)
    parser.add_argument("-c", "--config",
                        help="path to config file, "
                             "multiple files (split by comma) are supported "
                             "(later is prior, e.g. -c \"base.yaml, override.yaml\"). "
                             "Dirs are supported: every YAML file in the subtree "
                             "are treated as config files "
                             "(files under dir are sorted in alphabetical order). "
                             f"Environment variable: {CONFIG_ENV_VAR}. "
                             f"Defaults to \"{DEFAULT_CONFIG_FILE}\"")

    subcommands = parser.add_subparsers(title="subcommands",
                                        dest="subcommands",  # for args.subcommands below
                                        help="use \"bruniceps <subcommand> -h\" for more information about that topic.")

    subcommands_sync = subcommands.add_parser("sync", description=sync.__doc__)
    # subcommands_sync.add_argument("-d", help="example to add more args to sync")
    subcommands_dry_run = subcommands.add_parser("dry-run", description=dry_run.__doc__)

    args = parser.parse_args()

    config_paths = args.config or os.environ.get(CONFIG_ENV_VAR) or DEFAULT_CONFIG_FILE
    config = load_config(config_paths)

    match args.subcommands:
        case "sync":
            sync(config)
        case "dry-run":
            dry_run(config)


if __name__ == '__main__':
    main()
