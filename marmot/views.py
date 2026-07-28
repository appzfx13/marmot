# marmot/views.py - Add at bottom (main app)
from django.http import Http404
from django.shortcuts import render

def handler404(request, exception):
    return render(request, '404.html', status=404)