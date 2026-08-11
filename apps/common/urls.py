from django.urls import path
from .views import HomePageView

app_name = 'common'

urlpatterns = [
    path('', HomePageView.as_view(), name='home_page'),
]