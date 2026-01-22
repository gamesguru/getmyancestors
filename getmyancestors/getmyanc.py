#!/usr/bin/env python3
# coding: utf-8

# global imports
from __future__ import print_function

import asyncio
import getpass
import os
import re
import sys
import time
from datetime import datetime
from typing import List

import typer

from getmyancestors.classes.session import CachedSession, GMASession, Session
from getmyancestors.classes.tree import Tree

app = typer.Typer(
    help="Retrieve GEDCOM data from FamilySearch Tree",
    add_completion=True,
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


@app.command()
def main(
    username: str = typer.Option(
        None, "-u", "--username", metavar="<STR>", help="FamilySearch username"
    ),
    password: str = typer.Option(
        None, "-p", "--password", metavar="<STR>", help="FamilySearch password"
    ),
    individuals: List[str] = typer.Option(
        None,
        "-i",
        "--individuals",
        metavar="<STR>",
        help="List of individual FamilySearch IDs for whom to retrieve ancestors",
    ),
    exclude: List[str] = typer.Option(
        None,
        "-e",
        "--exclude",
        metavar="<STR>",
        help="List of individual FamilySearch IDs to exclude from the tree",
    ),
    ascend: int = typer.Option(
        4, "-a", "--ascend", metavar="<INT>", help="Number of generations to ascend [4]"
    ),
    descend: int = typer.Option(
        0,
        "-d",
        "--descend",
        metavar="<INT>",
        help="Number of generations to descend [0]",
    ),
    distance: int = typer.Option(
        0,
        "--distance",
        metavar="<INT>",
        help="The maxium distance from the starting individuals [0]. If distance is set, ascend and descend will be ignored.",
    ),
    only_blood_relatives: bool = typer.Option(
        False,
        "--only-blood-relatives",
        help="Only include blood relatives in the tree [False]",
    ),
    marriage: bool = typer.Option(
        False,
        "-m",
        "--marriage",
        help="Add spouses and couples information [False]",
    ),
    cache: bool = typer.Option(
        True, "--cache/--no-cache", help="Enable/Disable http cache [True]"
    ),
    cache_control: bool = typer.Option(
        True,
        "--cache-control/--no-cache-control",
        help="Disable cache-control (use dumb cache) [True]",
    ),
    get_contributors: bool = typer.Option(
        False,
        "-r",
        "--get-contributors",
        help="Add list of contributors in notes [False]",
    ),
    get_ordinances: bool = typer.Option(
        False,
        "-c",
        "--get_ordinances",
        help="Add LDS ordinances (need LDS account) [False]",
    ),
    verbose: bool = typer.Option(
        False, "-v", "--verbose", help="Increase output verbosity [False]"
    ),
    timeout: int = typer.Option(
        60, "-t", "--timeout", metavar="<INT>", help="Timeout in seconds [60]"
    ),
    rate_limit: int = typer.Option(
        5,
        "-R",
        "--rate-limit",
        metavar="<INT>",
        help="Maximum requests per second [5]",
    ),
    xml: bool = typer.Option(
        False,
        "-x",
        "--xml",
        help="To print the output in Gramps XML format [False]",
    ),
    show_password: bool = typer.Option(
        False, "--show-password", help="Show password in .settings file [False]"
    ),
    save_settings: bool = typer.Option(
        False, "--save-settings", help="Save settings into file [False]"
    ),
    geonames: str = typer.Option(
        None,
        "-g",
        "--geonames",
        metavar="<STR>",
        help="Geonames.org username in order to download place data",
    ),
    client_id: str = typer.Option(
        None, "--client_id", metavar="<STR>", help="Use Specific Client ID"
    ),
    redirect_uri: str = typer.Option(
        None, "--redirect_uri", metavar="<STR>", help="Use Specific Redirect Uri"
    ),
    creation_date: str = typer.Option(
        None,
        "--creation-date",
        metavar="<ISO8601>",
        help="Override creation date in GEDCOM header (YYYY-MM-DDTHH:MM:SS)",
    ),
    outfile: str = typer.Option(
        None, "-o", "--outfile", metavar="<FILE>", help="output GEDCOM file [stdout]"
    ),
    logfile: str = typer.Option(
        None, "-l", "--logfile", metavar="<FILE>", help="output log file [stderr]"
    ),
    extra_individuals: List[str] = typer.Argument(None, hidden=True),
):
    """
    Retrieve GEDCOM data from FamilySearch Tree
    """
    # NOISY DEBUG FOR CI
    if os.environ.get("GMA_DEBUG"):
        print(
            f"DEBUG: GMA_OFFLINE_MODE={os.environ.get('GMA_OFFLINE_MODE')}",
            file=sys.stderr,
        )
        print(f"DEBUG: GMA_DEBUG={os.environ.get('GMA_DEBUG')}", file=sys.stderr)
    if extra_individuals:
        if individuals is None:
            individuals = []
        individuals.extend(extra_individuals)

    # dummy translation function
    def _(s):
        return s

    # Forces stdout to use UTF-8 or at least not crash on unknown characters
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # Manually handle logfile opening (FileType is deprecated)
    logfile_handle = None
    if logfile:
        try:
            # pylint: disable=consider-using-with
            logfile_handle = open(logfile, "w", encoding="UTF-8")
        except OSError as e:
            print(f"Could not open logfile: {e}", file=sys.stderr)
            raise typer.Exit(code=2) from None

    if individuals:
        for fid in individuals:
            if not re.fullmatch(r"[A-Z0-9]{4}-[A-Z0-9]{3}", fid):
                print("Invalid FamilySearch ID: " + fid, file=sys.stderr)
                raise typer.Exit(code=1)
    if exclude:
        for fid in exclude:
            if not re.fullmatch(r"[A-Z0-9]{4}-[A-Z0-9]{3}", fid):
                print("Invalid FamilySearch ID: " + fid, file=sys.stderr)
                raise typer.Exit(code=1)

    if not username:
        if verbose:
            print("⚠️ Warning: getting username from command line, env var not set.")
        username = input("Enter FamilySearch username: ")
    if not password:
        if os.getenv("FAMILYSEARCH_PASS"):
            if verbose:
                print("✅ Using password from env var.")
            password = os.getenv("FAMILYSEARCH_PASS") or ""
        else:
            if verbose:
                print("⚠️ Warning: getting password from command line, env var not set.")
            password = getpass.getpass("Enter FamilySearch password: ")

    if verbose:
        print("✅ Using username: " + username)
        print(f"✅ Using password: {len(password)} digits long.")

    time_count = time.time()

    # Report settings used when getmyancestors is executed
    if save_settings and outfile and outfile != "<stdout>":

        formatting = "{:74}{:\\t>1}\\n"
        settings_name = outfile.rsplit(".", 1)[0] + ".settings"
        try:
            with open(settings_name, "w", encoding="utf-8") as settings_file:
                settings_file.write(
                    formatting.format("time stamp: ", time.strftime("%X %x %Z"))
                )
                # Reconstruct args for settings file
                # This is a bit manual since we don't have Namespace, but feasible
                params = locals()
                for key, val in params.items():
                    if key in [
                        "settings_file",
                        "formatting",
                        "settings_name",
                        "_",
                        "logfile_handle",
                        "time_count",
                        "params",
                    ]:
                        continue
                    if key == "password" and not show_password:
                        val = "******"
                    settings_file.write(
                        formatting.format(f"--{key.replace('_', '-')}", str(val))
                    )

        except OSError as exc:
            print(
                "Unable to write %s: %s" % (settings_name, repr(exc)), file=sys.stderr
            )

    # initialize a FamilySearch session and a family tree object
    print(_("Login to FamilySearch..."), file=sys.stderr)

    # Common params
    session_kwargs = {
        "username": username,
        "password": password,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "verbose": verbose,
        "logfile": logfile_handle,
        "timeout": timeout,
        "cache_control": cache_control,
        "requests_per_second": rate_limit,
    }

    if cache:
        print(_("Using cache..."), file=sys.stderr)
        fs: GMASession = CachedSession(**session_kwargs)  # type: ignore
    else:
        fs = Session(**session_kwargs)

    if not fs.logged:
        raise typer.Exit(code=2)
    _ = fs._

    creation_dt = None
    if creation_date:
        try:
            creation_dt = datetime.fromisoformat(creation_date)
        except ValueError:
            print(
                f"Invalid creation date format: {creation_date}. Expected ISO 8601 (YYYY-MM-DDTHH:MM:SS)",
                file=sys.stderr,
            )
            raise typer.Exit(code=1) from None

    tree = Tree(
        fs,
        exclude=exclude,
        geonames_key=geonames,
        only_blood_relatives=only_blood_relatives,
        creation_date=creation_dt,
    )

    # check LDS account
    if get_ordinances:
        test = fs.get_url(
            "/service/tree/tree-data/reservations/person/%s/ordinances" % fs.fid, {}
        )
        if not test or test.get("status") != "OK":
            raise typer.Exit(code=2)

    success = False
    try:
        # add list of starting individuals to the family tree
        todo_list = individuals if individuals else ([fs.fid] if fs.fid else [])
        if not todo_list:
            raise typer.Exit(code=1)
        print(_("Downloading starting individuals..."), file=sys.stderr)
        tree.add_indis(todo_list)

        # download ancestors
        if distance == 0:
            todo = set(tree.indi.keys())
            done = set()
            for i in range(ascend):
                if not todo:
                    break
                done |= todo
                print(
                    _("Downloading %s. of generations of ancestors...") % (i + 1),
                    file=sys.stderr,
                )
                todo = tree.add_parents(sorted(todo)) - done

            # download descendants
            todo = set(tree.indi.keys())
            done = set()
            for i in range(descend):
                if not todo:
                    break
                done |= todo
                print(
                    _("Downloading %s. of generations of descendants...") % (i + 1),
                    file=sys.stderr,
                )
                todo = tree.add_children(sorted(todo)) - done

            # download spouses
            if marriage:
                print(
                    _("Downloading spouses and marriage information..."),
                    file=sys.stderr,
                )
                todo = set(tree.indi.keys())
                tree.add_spouses(sorted(todo))

        else:
            todo_bloodline = set(tree.indi.keys())
            # TODO: check for regressons here, since we removed a set()
            done = set()
            for dist in range(distance):
                if not todo_bloodline:
                    break
                done |= todo_bloodline
                print(
                    _("Downloading individuals at distance %s...") % (dist + 1),
                    file=sys.stderr,
                )
                parents = tree.add_parents(sorted(todo_bloodline)) - done
                children = tree.add_children(sorted(todo_bloodline)) - done

                if marriage:
                    print(
                        _("Downloading spouses and marriage information..."),
                        file=sys.stderr,
                    )
                    todo = set(tree.indi.keys())
                    tree.add_spouses(sorted(todo))

                todo_bloodline = parents | children

        # download ordinances, notes and contributors
        async def download_stuff(loop):
            futures = set()
            for fid, indi in tree.indi.items():
                futures.add(loop.run_in_executor(None, indi.get_notes))
                if get_ordinances:
                    futures.add(loop.run_in_executor(None, tree.add_ordinances, fid))
                if get_contributors:
                    futures.add(loop.run_in_executor(None, indi.get_contributors))
            for fam in tree.fam.values():
                futures.add(loop.run_in_executor(None, fam.get_notes))
                if get_contributors:
                    futures.add(loop.run_in_executor(None, fam.get_contributors))
            for future in futures:
                await future

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        print(
            _("Downloading notes")
            + (
                (("," if get_contributors else _(" and")) + _(" ordinances"))
                if get_ordinances
                else ""
            )
            + (_(" and contributors") if get_contributors else "")
            + "...",
            file=sys.stderr,
        )
        loop.run_until_complete(download_stuff(loop))

        success = True

    finally:
        if logfile_handle:
            logfile_handle.close()

        if success:
            tree.reset_num()
            output_format = "XML" if xml else "GEDCOM"
            print(_("Generating output..."), file=sys.stderr)
            print(
                _("Generating %s with %d individuals...")
                % (output_format, len(tree.indi)),
                file=sys.stderr,
            )
            if xml:
                if outfile:
                    with open(outfile, "wb") as f:
                        tree.printxml(f)
                else:
                    tree.printxml(sys.stdout.buffer)
            else:
                if outfile:
                    with open(outfile, "w", encoding="UTF-8") as f_ged:
                        tree.print(f_ged)
                else:
                    tree.print(sys.stdout)

            # Statistics printout (abbreviated for brevity)
            print(
                _(
                    "Downloaded %s individuals, %s families, %s sources and %s notes "
                    "in %s seconds with %s HTTP requests."
                )
                % (
                    str(len(tree.indi)),
                    str(len(tree.fam)),
                    str(len(tree.sources)),
                    str(len(tree.notes)),
                    str(round(time.time() - time_count)),
                    str(fs.counter),
                ),
                file=sys.stderr,
            )


if __name__ == "__main__":
    app()
