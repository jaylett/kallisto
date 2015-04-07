import errno
import os

from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ObjectDoesNotExist

from apps.transcripts.models import Mission, MissionExporter

class Command(BaseCommand):
    help = """Export a cleaned transcript and basic metadata file for use in
Spacelog.

If a transcript name isn't passed, the default is TEC."""

    args = "<mission-short-name> <export-dir> [<transcript-name>]"

    def handle(self, *args, **kwargs):
        if len(args) < 2 or len(args) > 3:
            raise CommandError("Wrong number of arguments.")

        try:
            mission = Mission.objects.get(short_name=args[0])
        except ObjectDoesNotExist:
            raise CommandError("No such mission.")

        export_dir = args[1]
        self._mkdir(os.path.join(export_dir, "transcripts"))

        main_transcript_name = "TEC"
        if len(args) > 2:
            main_transcript_name = args[2]

        exporter = MissionExporter(mission, main_transcript_name)

        with open(os.path.join(export_dir, exporter.main_transcript_path()), "w") as f:
            f.write(exporter.main_transcript())

        with open(os.path.join(export_dir, exporter.meta_path()), "w") as f:
            f.write(exporter.meta())

    def _mkdir(self, path):
        try:
            os.makedirs(path)
        except OSError as err:
            if err.errno == errno.EEXIST and os.path.isdir(path):
                pass
            else:
                raise CommandError("Cannot create directory '%s'" % path)
