# pylint: disable=C0103
from django.conf.urls import patterns, url
from . import views


urlpatterns = patterns(
    '',
    url(r'^$', views.RuntimeView.as_view(), name='runtime'),
)
