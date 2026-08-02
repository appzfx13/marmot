# mixins.py
from django.contrib import messages
from django.shortcuts import render

class HtmxMessageMixin:
    """
    Mixin for Class-Based Views (CreateView, UpdateView, DeleteView) 
    that attaches user-friendly messages from constants.py on successful CRUD operations.
    """
    success_message = ""

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.success_message:
            messages.success(self.request, self.success_message)
        return response

    def delete(self, request, *args, **kwargs):
        response = super().delete(request, *args, **kwargs)
        if self.success_message:
            messages.success(self.request, self.success_message)
        return response



class HtmxModalMixin:
    """
    Mixin to serve a partial modal template for HTMX requests,
    falling back to the standard page template otherwise.
    """
    modal_template_name = None

    def get_template_names(self):
        # Check if the request was made by HTMX
        if self.request.htmx and self.modal_template_name:
            return [self.modal_template_name]
        return super().get_template_names()