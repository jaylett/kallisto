from django.conf import settings
from django.conf.urls import patterns, include, url
from django.conf.urls.static import static
from django.contrib import admin
import exceptional_middleware

urlpatterns = patterns(
    '',
    url(r'^$', 'apps.homepage.views.homepage', name='homepage'),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^(?P<slug>[0-9A-Za-z]+)/$', 'apps.transcripts.views.clean', name='mission-clean-next'),
    url(r'^(?P<slug>[0-9A-Za-z]+)/(?P<page>[0-9]+)/$', 'apps.transcripts.views.page', name='mission-page'),
    url(r'^(?P<slug>[0-9A-Za-z]+)/export/$', 'apps.transcripts.views.export', name='mission-export'),

    url(r'^account/register/$', 'apps.people.views.register', name='register'),
    url(r'^account/registered/$', 'apps.people.views.registered', name='registered'),
    url(r'^email-confirm/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
        'apps.people.views.confirm_email_address',
        name='confirm_email_address',
    ),
    # Logout and (some) password management -- only the things we
    # have to modify from the built-in behaviour.
    url(r'^account/logout/$', 'apps.people.views.logout', name='logout'),
    url(r'^account/password/reset/(?P<uid>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$', 'apps.people.views.password_reset_confirm', { 'post_reset_redirect': '/' }, name='password_reset_confirm'),
) + patterns(
    # And the rest of registration/account stuff.
    'django.contrib.auth.views',
    url(r'^account/login/$', 'login', name='login'),
    url(r'^account/password/change/$', 'password_change', name='password_change'),
    url(r'^account/password/change/done/$', 'password_change_done', name='password_change_done'),
    url(r'^account/password/forgot/$', 'password_reset', name='password_reset'),
    url(r'^account/password/forgot/done/$', 'password_reset_done', name='password_reset_done'),
)

handler403 = exceptional_middleware.handler403
handler404 = exceptional_middleware.handler404
handler500 = exceptional_middleware.handler500

# For testing. Or fun.
urlpatterns += patterns(
    '',
    url(r'^http/', include('exceptional_middleware.urls')),
)

# In debug, for media
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL, document_root=settings.MEDIA_ROOT
    )
