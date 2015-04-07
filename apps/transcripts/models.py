import json
from datetime import timedelta
from django.db import models, transaction
from django.db.models import Q, F
from django.utils.translation import ugettext_lazy as _
from django.utils import timezone

from apps.people.models import User
from lib.media import core_media_filename, MigratableImageField


class LockExpired(Exception):
    pass


class MissionManager(models.Manager):

    def current(self):
        return Mission.objects.filter(active=True)[0]


class Mission(models.Model):
    name = models.CharField(max_length=500,
        help_text=_('Full name (eg Mercury-Atlas 7).'))
    short_name = models.CharField(max_length=10,
        help_text=_('Short name (eg MA7).'))
    start = models.DateField()
    end = models.DateField()
    patch = MigratableImageField(
        height_field='patch_height',
        width_field='patch_width',
        upload_to=lambda i, f: core_media_filename(
            'mission/patch',
            i.short_name,
            f
        )
    )
    patch_width = models.IntegerField(
        default=0,
        blank=True,
        null=True,
        editable=False
    )
    patch_height = models.IntegerField(
        default=0,
        blank=True,
        null=True,
        editable=False
    )
    active = models.BooleanField(
        default=True,
        help_text=_('Are we currently cleaning this mission?'),
    )
    wiki = models.URLField(
        null=True,
        blank=True,
        help_text=_('URL of wiki page for useful notes.'),
    )

    objects = MissionManager()

    def release_expired_locks(self):
        self.pages.filter(
            locked_by__isnull=False,
            locked_until__lt=timezone.now()
        ).update(
            locked_by=None,
            locked_until=None
        )
    
    def next_page_for_user(self, user):
        # this is somewhat more conservative -- in terms of taking
        # into account already-locked pages -- than we strictly need
        # right now, but should clear up border cases well.

        def _lock_pages_for_user(pages, user, n=1):
            # this is a bit awkward; we have to convert from a QuerySet
            # into a list then back into a QuerySet because we want to
            # be able to pass QuerySets around (since they're nice) but
            # we also need to restrict to a number of pages to operate
            # on, which we can't do and subsequently run .update().
            #
            # This strictly means that between the time that we pull
            # things from the database (in the [:n] slice) and the time
            # that we run the update, the candidates may have changed
            # beneath us. The Q(...) filters prevent us from locking
            # pages we shouldn't, but it's possible that we'll miss out
            # on a page we might otherwise have got.
            #
            # We could put the values_list()...update() block in a
            # transaction, which would avoid this problem, but it does
            # so at a concurrency cost.
            page_pks = list(pages.values_list('pk', flat=True)[:n])
            to_lock = Page.objects.filter(
                pk__in=page_pks,
            )
            until = timezone.now() + timedelta(minutes=5)
            updated = to_lock.filter(
                approved=False
            ).filter(
                Q(locked_by__isnull=True) |
                Q(locked_by=user) |
                Q(locked_by__isnull=False, locked_until__lt=timezone.now())
            ).update(
                locked_by=user,
                locked_until=until,
            )
            return to_lock.filter(
                locked_by=user,
                locked_until__gte=timezone.now(),
            )

        prelocked_candidates = self.pages.filter(
            locked_by=user,
            approved=False,
        ).exclude(
            revisions__by=user,
        )

        locked_pages = _lock_pages_for_user(
            prelocked_candidates,
            user,
            1
        )
        if len(locked_pages) > 0:
            return locked_pages[0]

        self.release_expired_locks()
        unlocked_candidates = self.pages.filter(
            locked_by__isnull=True,
            approved=False,
        ).exclude(
            revisions__by=user,
        )
        locked_pages = _lock_pages_for_user(
            unlocked_candidates,
            user,
            1
        )
        if len(locked_pages) > 0:
            return locked_pages[0]

        return None

    def approved_pages(self):
        return self.pages.filter(approved=True)

    def cleaned_pages(self):
        return self.pages.filter(revisions__id__isnull=False).distinct()
    
    def __unicode__(self):
        return self.name

    class Meta:
        ordering = ('start', )


class Page(models.Model):
    mission = models.ForeignKey(Mission, related_name='pages')
    number = models.PositiveIntegerField()
    original = MigratableImageField(
        height_field='original_height',
        width_field='original_width',
        upload_to=lambda i, f: core_media_filename(
            'mission/page',
            i.mission.short_name,
            f
        )
    )
    original_width = models.IntegerField(
        default=0,
        blank=True,
        null=True,
        editable=False
    )
    original_height = models.IntegerField(
        default=0,
        blank=True,
        null=True,
        editable=False
    )
    original_text = models.TextField()
    approved = models.BooleanField(
        default=False,
        help_text=_('Is the latest revision approved?'),
    )

    locked_by = models.ForeignKey(
        'people.User',
        related_name='pages_locked',
        blank=True,
        null=True
    )
    locked_until = models.DateTimeField(blank=True, null=True)

    @property
    def text(self):
        try:
            rev = self.revisions.last()
            if rev is not None:
                return rev.text
        except Revision.DoesNotExist:
            pass
        
        return self.original_text

    def create_revision(self, text, user):
        with transaction.atomic():
            # The lock should prevent another revision being created
            # in the interim (since we were working off a previous
            # revision or the original, we'd have been overwriting
            # their changes).
            previous_text = self.text
            revision = Revision.objects.create(
                page = self,
                text = text,
                by = user,
            )
            update = {}
            # mark if the page is now approved
            if previous_text == text:
                update['approved'] = True
                User.objects.filter(
                    pk=user.pk,
                ).update(
                    pages_approved=F('pages_approved')+1,
                    score=F('score')+1,
                )
            else:
                User.objects.filter(
                    pk=user.pk,
                ).update(
                    pages_cleaned=F('pages_cleaned')+1,
                    score=F('score')+1,
                )
            # and unlock the page
            unlocked = Page.objects.filter(
                mission = self.mission,
                number = self.number,
                locked_by = user,
                approved = False,
            ).update(
                locked_by = None,
                locked_until = None,
                **update
            )
            if unlocked != 1:
                raise LockExpired(_("Lock expired before save."))

    def is_locked(self):
        return (
            self.locked_by is not None and self.locked_until >= timezone.now()
        )
            
    def __unicode__(self):
        return _('%(mission)s page %(page)s') % {
            'mission': self.mission.name,
            'page': self.number,
        }

    class Meta:
        ordering = ('mission', 'number',)
        unique_together = ('mission', 'number',)


class Revision(models.Model):
    page = models.ForeignKey(Page, related_name='revisions')
    text = models.TextField()
    by = models.ForeignKey('people.User', related_name='page_revisions')
    when = models.DateTimeField(auto_now_add=True)

    def __unicode__(self):
        return _(u"p%(page)s of %(mission)s by %(by)s") % {
            'page': self.page.number,
            'mission': self.page.mission.name,
            'by': self.by.name
        }

    class Meta:
        unique_together = ('page', 'by')
        ordering = ('when',)


class MissionExporter(object):
    """Exports a mission so it can be used in Spacelog"""

    def __init__(self, mission, main_transcript_name="TEC"):
        self.mission = mission
        self.main_transcript_name = main_transcript_name

    def main_transcript(self):
        """Returns the text of the mission's main transcript"""
        main_transcript = ""
        for page in self.mission.pages.all():
            main_transcript += "\tPage %d\n" % page.number
            main_transcript += "\tApproved? %s\n" % page.approved
            main_transcript += page.text
            main_transcript += "\n"
        return main_transcript

    def main_transcript_path(self):
        """Returns the path where the main transcript should be written,
        relative to the mission's root directory."""
        return "transcripts/%s" % (self.main_transcript_name,)

    def meta(self):
        """Returns the JSON of the mission's _meta transcript"""
        upper_title, lower_title = self.mission.name.split(" ", 1)
        meta = {
            "name": self.mission.short_name.lower(),
            "incomplete": True,
            "subdomains": [self.mission.short_name.lower()],
            "copy": {
                "title": self.mission.name,
                "upper_title": upper_title,
                "lower_title": lower_title,
                "cleaners": self._cleaners(),
            },
            "main_transcript": "%s/%s" % (
                self.mission.short_name.lower(),
                self.main_transcript_name,
            ),
            "utc_launch_time": self.mission.start.isoformat(),
        }
        return json.dumps(meta, indent=4) + "\n"

    def meta_path(self):
        """Returns the path where the meta file should be written,
        relative to the mission's root directory."""
        return "transcripts/_meta"

    def _cleaners(self):
        cleaners = set()
        for page in self.mission.pages.all():
            for revision in page.revisions.all():
                cleaners.add(revision.by.name)
        cleaners = list(cleaners)
        cleaners.sort()
        return cleaners
