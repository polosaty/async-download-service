import argparse
import asyncio
import datetime
import hashlib
import logging
import os
from subprocess import PIPE

import aiofiles
from aiohttp import web

logging.basicConfig(level=os.getenv("LOG_LEVEL", logging.INFO))

INTERVAL_SECS = 1  # sec
BATCH_SIZE = 100  # KiB
DIRECTORIES = {}
PHOTOS_DIR = os.getenv("PHOTOS_DIR", "test_photos")
PAGE_404 = "/404"
DELAY = os.getenv("DELAY", 0)  # sec
PORT = os.getenv("PORT", 8080)


async def kill_process(process):
    if process and process.returncode is None:
        process.kill()
        await process.communicate()


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
        directory = os.path.join(request.app['photos_dir'], DIRECTORIES[archive_hash])
        files = [file for file in os.listdir(directory)]
        archive_offset = 0
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
                logging.debug("Sending archive chunk with offset: %r", archive_offset)
                buf = await process.stdout.read(BATCH_SIZE * 1024)
                archive_offset += len(buf)
                await response.write(buf)

                if request.app.get('delay'):
                    await asyncio.sleep(request.app.get('delay'))
            return response
        except asyncio.CancelledError:
            logging.debug("Download was interrupted")
            await kill_process(process)
            raise
        finally:
            await kill_process(process)
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
    app = web.Application()

    app['photos_dir'] = args.photos_dir or PHOTOS_DIR
    app['delay'] = args.delay or DELAY

    for directory_name in os.listdir(PHOTOS_DIR):
        DIRECTORIES[hashlib.md5(directory_name.encode()).hexdigest()] = directory_name

    logging.debug("photo rirectories %r", DIRECTORIES)

    app.add_routes(
        [
            web.get("/", handle_index_page),
            web.get("/archive/{archive_hash}/", archivate),
            web.get(PAGE_404, handle_404_page),
        ]
    )
    web.run_app(app, port=args.port)
