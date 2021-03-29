import argparse
import asyncio
import datetime
import hashlib
import logging
import os
from subprocess import PIPE

import aiofiles
from aiohttp import web

logging.basicConfig(level=logging.DEBUG)

INTERVAL_SECS = 1  # sec
BATCH_SIZE = 100  # KiB
DIRECTORIES = {}
PHOTOS_DIR = os.getenv("PHOTOS_DIR", "test_photos")
PAGE_404 = "/404"
DELAY = os.getenv("DELAY", 0)  # sec
PORT = os.getenv("PORT", 8080)


async def archivate(request: web.BaseRequest):
    archive_hash = request.match_info.get("archive_hash")
    if archive_hash == "7kna":
        response = web.StreamResponse()
        response.headers["Content-Type"] = "text/html"
        await response.prepare(request)

        while True:
            formatted_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"{formatted_date}<br>"

            await response.write(message.encode("utf-8"))

            await asyncio.sleep(INTERVAL_SECS)

        return response

    elif archive_hash in DIRECTORIES:
        directory = os.path.join(PHOTOS_DIR, DIRECTORIES[archive_hash])
        files = [f for f in os.listdir(directory)]
        tell = 0
        process = await asyncio.create_subprocess_exec(
            "zip", "-", *files, stdout=PIPE, stderr=PIPE, cwd=directory
        )

        try:
            response = web.StreamResponse()
            response.headers["Content-Type"] = "application/zip"
            response.headers[
                "Content-Disposition"
            ] = 'attachment; filename="photos.zip"'
            await response.prepare(request)

            while not process.stdout.at_eof():
                logging.debug("Sending archive chunk with offset: %r", tell)
                buf = await process.stdout.read(BATCH_SIZE * 1024)
                tell += len(buf)
                await response.write(buf)

                if DELAY:
                    await asyncio.sleep(DELAY)
            return response
        except asyncio.CancelledError:
            logging.debug("Download was interrupted")
            process.kill()
        finally:
            if process.returncode is None:
                process.kill()
                await process.communicate()
            logging.debug("Archive sending finished")

    else:
        raise web.HTTPFound(PAGE_404)


async def handle_index_page(request):
    async with aiofiles.open("index.html", mode="r") as index_file:
        index_contents = await index_file.read()
    return web.Response(text=index_contents, content_type="text/html")


async def handle_404_page(request):
    return web.Response(
        text="Архив не существует или был удален", content_type="text/html"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Zip and photos to download.")
    parser.add_argument("--port", type=int, help="port number", default=PORT)

    parser.add_argument(
        "--photos-dir",
        dest="photos_dir",
        type=str,
        help=f"directory with photos directories (default: {PHOTOS_DIR})",
    )

    parser.add_argument(
        "--delay", dest="delay", type=int, help="add delay on every chunk"
    )

    args = parser.parse_args()
    if args.photos_dir:
        globals()["PHOTOS_DIR"] = args.photos_dir

    if args.delay:
        globals()["DELAY"] = args.delay

    app = web.Application()

    for d in os.listdir(PHOTOS_DIR):
        DIRECTORIES[hashlib.md5(d.encode()).hexdigest()] = d

    logging.debug("photo rirectories %r", DIRECTORIES)

    app.add_routes(
        [
            web.get("/", handle_index_page),
            web.get("/archive/{archive_hash}/", archivate),
            web.get(PAGE_404, handle_404_page),
        ]
    )
    web.run_app(app, port=args.port)
