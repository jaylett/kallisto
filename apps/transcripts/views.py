from zipfile import ZipFile
from StringIO import StringIO
from django import forms
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.utils.translation import ugettext_lazy as _
from django.views.generic import DetailView, UpdateView
from .models import Mission, Page, Revision, LockExpired, MissionExporter


class CleanNext(DetailView):
    model = Mission
    slug_field = 'short_name'
    
    def get(self, request, *args, **kwargs):
        mission = self.get_object()
        page = mission.next_page_for_user(request.user)
        if page is None:
            return HttpResponseRedirect(reverse('homepage'))
        else:
            return HttpResponseRedirect(
                reverse(
                    'mission-page',
                    kwargs={
                        'slug': mission.short_name,
                        'page': page.number,
                    }
                )
            )
clean = login_required(CleanNext.as_view())


class CleanPage(UpdateView):
    model = Page
    template_name_suffix = '_clean'

    def get_initial(self):
        return {
            'text': self.object.text,
        }
    
    def get_form_class(self):
        obj = self.object
        user = self.request.user

        class MakeRevision(forms.Form):
            text = forms.CharField(
                label=_(u'Cleaned page'),
                widget=forms.Textarea(
                    attrs={
                        'cols': 100,
                        'rows': 35
                    },
                ),
            )

            def save(self):
                obj.create_revision(
                    self.cleaned_data['text'],
                    user,
                )
                return obj

        return MakeRevision

    def get_form_kwargs(self):
        kwargs = super(CleanPage, self).get_form_kwargs()
        del kwargs['instance']
        return kwargs

    def get_context_data(self, **kwargs):
        return super(CleanPage, self).get_context_data(**kwargs)
    
    def get_object(self, queryset=None):
        try:
            mission = Mission.objects.get(short_name=self.kwargs.get('slug'))
        except Mission.DoesNotExist:
            raise Http404

        try:
            page = mission.pages.get(number=int(self.kwargs.get('page')))
        except Page.DoesNotExist:
            raise Http404
        except ValueError:
            # could not convert number URL kwarg to int
            raise Http404

        return page

    def form_valid(self, form):
        try:
            form.save()
            return HttpResponseRedirect(self.get_success_url())
        except LockExpired:
            form.add_error(
                None,
                forms.ValidationError(
                    _(
                        u"Lock expired; please go back to "
                        u"the home page to continue cleaning."
                    )
                ),
            )
            return self.form_invalid(form)
    
    def get_success_url(self):
        return reverse(
            'mission-clean-next',
            kwargs={
                'slug': self.object.mission.short_name,
            },
        )
page = login_required(CleanPage.as_view())


class ExportMission(DetailView):
    model = Mission
    slug_field = 'short_name'

    def get(self, request, *args, **kwargs):
        response = HttpResponse(self._zip_data().read())
        response['Content-Disposition'] = 'attachment; filename=%s.zip' % (self._mission_short_name,)
        response['Content-Type'] = 'application/x-zip'
        return response

    def _zip_data(self):
        exporter = self._get_exporter()
        zip_data = StringIO()
        with ZipFile(zip_data, mode='w') as zip_file:
            zip_file.writestr(
                "%s/%s" % (self._mission_short_name, exporter.main_transcript_path()),
                unicode(exporter.main_transcript()).encode("utf-8"),
            )
            zip_file.writestr(
                "%s/%s" % (self._mission_short_name, exporter.meta_path()),
                unicode(exporter.meta()).encode("utf-8"),
            )
        zip_data.seek(0)
        return zip_data

    def _get_exporter(self):
        return MissionExporter(self.get_object())

    @property
    def _mission_short_name(self):
        return self.get_object().short_name

export = login_required(ExportMission.as_view())
