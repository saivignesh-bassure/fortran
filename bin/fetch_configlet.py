#!/usr/bin/env python3
from datetime import datetime, timezone
import io
import json
import logging
import platform
import sys
import tarfile
import time
from urllib.request import urlopen
from urllib.error import HTTPError, URLError


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BACKOFF_TIME = 5  # in seconds
MAX_RETRIES = 5


def download_and_extract(url):
    try:
        with urlopen(url) as request:
            status = request.status
            response = request.read()
    except HTTPError as err:
        status = err.code
        response = err.reason
    except URLError as err:
        logger.error(err.reason)
        time.sleep(BACKOFF_TIME)
        return False
    if status >= 400:
        logger.error(f"Unexpected {status} status from download server: {response}")
        time.sleep(BACKOFF_TIME)
        return False

    logger.info("extracting...")
    with tarfile.open(fileobj=io.BytesIO(response), mode="r:*") as file:
        
        import os
        
        def is_within_directory(directory, target):
            
            abs_directory = os.path.abspath(directory)
            abs_target = os.path.abspath(target)
        
            prefix = os.path.commonprefix([abs_directory, abs_target])
            
            return prefix == abs_directory
        
        def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
        
            for member in tar.getmembers():
                member_path = os.path.join(path, member.name)
                if not is_within_directory(path, member_path):
                    raise Exception("Attempted Path Traversal in Tar File")
        
            tar.extractall(path, members, numeric_owner=numeric_owner) 
            
        
        safe_extract(file, path="bin/")
    return True


def get_os():
    os_ = platform.platform()
    if os_ == "Darwin":
        return "mac"
    elif os_ == "Windows":
        return "windows"
    return "linux"


def get_arch():
    return "64bit" if sys.maxsize > 2 ** 32 else "32bit"


def fetch_configlet():
    try:
        with urlopen(
            "https://api.github.com/repos/exercism/configlet/releases/latest"
        ) as request:
            status = request.status
            headers = dict(request.getheaders())
            response = request.read()
    except HTTPError as err:
        status = err.code
        headers = err.headers
        response = err.reason
    except URLError as err:
        logger.exception(err)
        time.sleep(BACKOFF_TIME)
        return 1
    if status >= 500:
        logger.info(f"Sleeping due to {status} response from API: {response}")
        time.sleep(BACKOFF_TIME)
        return 1
    if status == 403:
        wait_until = datetime.fromtimestamp(
            int(headers["X-RateLimit-Reset"]), timezone.utc
        )
        delta = wait_until - datetime.now(timezone.utc)
        seconds = delta.total_seconds()
        wait = seconds + 5 if seconds > BACKOFF_TIME else BACKOFF_TIME
        logger.info(f"Rate limited, sleeping {wait} seconds.")
        time.sleep(wait)
        return 1
    if status >= 400:
        logger.error(f"Received unexpected {status} response from API: {response}")
        return 1
    data = json.loads(response.decode("utf-8"))
    version = data["tag_name"]
    machine_info = f"{get_os()}-{get_arch()}"
    name = f"configlet-{machine_info}.tgz"
    for asset in data["assets"]:
        if asset["name"] == name:
            logger.info(f"Downloading configlet {version} for {machine_info}")
            for _ in range(MAX_RETRIES):
                if download_and_extract(asset["browser_download_url"]):
                    return 0
    return 1


def main():
    for _ in range(MAX_RETRIES):
        ret = fetch_configlet()
        if ret == 0:
            break
    return ret


if __name__ == "__main__":
    sys.exit(main())
