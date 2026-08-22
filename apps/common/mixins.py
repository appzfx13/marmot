from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import render
from django.views.generic import View


class HtmxMessageMixin:
    """Mixin for CBVs that attaches user-friendly messages from constants.py on successful CRUD operations."""
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
    """Mixin to serve a partial modal template for HTMX requests, falling back to page template otherwise."""
    modal_template_name = None

    def get_template_names(self):
        if self.request.htmx and self.modal_template_name:
            return [self.modal_template_name]
        return super().get_template_names()


class BaseHtmxScrollListView(View):
    """
    Reusable DRY base view for infinite scroll and Load More table pagination.
    Renders desktop rows or mobile cards based on the 'scroll_type' query parameter.
    """
    rows_template_name = ""
    cards_template_name = ""
    context_object_name = "object_list"
    paginate_by = getattr(settings, 'PAGINATION_COUNT', 10)
    page_kwarg = "page"

    def get_queryset(self):
        raise NotImplementedError("Subclasses of BaseHtmxScrollListView must implement get_queryset()")

    def get_paginate_by(self):
        return self.paginate_by

    def get_context_data(self, **kwargs):
        return kwargs

    def get(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        paginator = Paginator(queryset, self.get_paginate_by())
        page_number = request.GET.get(self.page_kwarg, 1)
        page_obj = paginator.get_page(page_number)

        query_params = request.GET.copy()
        query_params.pop(self.page_kwarg, None)
        query_params.pop('scroll_type', None)

        context = {
            self.context_object_name: page_obj,
            'page_obj': page_obj,
            'paginator': paginator,
            'current_filters': query_params.urlencode(),
        }
        context.update(self.get_context_data(**kwargs))

        scroll_type = request.GET.get('scroll_type', 'rows')
        if scroll_type == 'cards' and self.cards_template_name:
            return render(request, self.cards_template_name, context)
        return render(request, self.rows_template_name, context)