"""Command line entry point: ``canviewer --file LOG --dbc DB.dbc``."""

from __future__ import annotations

import logging
import threading
import webbrowser
from pathlib import Path

import click

from canviewer import __version__

DEFAULT_PORT = 8765


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="canviewer")
@click.option("--file", "-f", "log_file", required=True,
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="CAN log: .mf4, or .asc/.blf/.trc (converted to .mf4 and cached).")
@click.option("--dbc", "-d", required=True, envvar="CANVIEWER_DBC",
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="DBC file used to decode the log. [env: CANVIEWER_DBC]")
@click.option("--title", default=None, help="Title shown in the navbar (default: log file name).")
@click.option("--tz", default="UTC", envvar="CANVIEWER_TZ", show_default=True,
              help="IANA timezone for displayed timestamps, e.g. America/Los_Angeles. [env: CANVIEWER_TZ]")
@click.option("--host", default="127.0.0.1", show_default=True,
              help="Interface to bind. The explorer has no authentication; keep it on localhost.")
@click.option("--port", default=DEFAULT_PORT, show_default=True, help="Port to serve on.")
@click.option("--cache-dir", default=None, type=click.Path(file_okay=False, path_type=Path),
              help="Where converted logs are cached (default: ~/.canviewer-cache).")
@click.option("--no-browser", is_flag=True, help="Don't open the browser automatically.")
def main(log_file: Path, dbc: Path, title: str, tz: str, host: str, port: int,
         cache_dir: Path, no_browser: bool) -> None:
    """Explore a CAN log: drag signals into frames and plot them as discrete samples.

    \b
    Examples:
      canviewer -f capture.mf4 -d vehicle.dbc
      canviewer -f capture.asc -d vehicle.dbc --tz America/Los_Angeles --port 9000
    """
    import pandas as pd

    from canviewer.app import create_app
    from canviewer.data import load_log

    try:
        pd.Timestamp.now(tz=tz)
    except Exception as exc:  # noqa: BLE001 - any tz failure is a usage error
        raise click.BadParameter(f"unknown timezone {tz!r}", param_hint="--tz") from exc

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    click.echo(f"  loading  {log_file}")
    try:
        data = load_log(str(log_file), str(dbc), tz=tz, cache_dir=cache_dir, title=title)
    except (ValueError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"  decoded  {len(data.catalog)} signals in {len(data.messages)} messages")

    app = create_app(data)
    url = f"http://{host}:{port}"
    click.echo(f"  serving  {url}  (Ctrl-C to quit)")
    if not no_browser:
        # Open once the server is up rather than racing it.
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    app.run(host=host, port=port, debug=False)
