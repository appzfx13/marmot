import django_filters
from django.db.models import Q

from apps.trade_config.models import TradeExecConfig



class TradeExecConfigFilter(django_filters.FilterSet):
    # Filter by Config Name (icontains)
    name = django_filters.CharFilter(
        field_name='name',
        lookup_expr='icontains'
    )
    
    # Filter by Marmot User details (username, email, first_name, last_name)
    q = django_filters.CharFilter(
        method='filter_user_search',
        label='User Search'
    )
    
    # Filter by Active Status (is_active)
    is_active = django_filters.BooleanFilter(
        field_name='is_active'
    )

    class Meta:
        model = TradeExecConfig
        fields = ['name', 'q', 'is_active']

    def filter_user_search(self, queryset, name, value):
        if not value:
            return queryset
        value = value.strip()
        return queryset.filter(
            Q(admins_user__username__icontains=value) |
            Q(admins_user__email__icontains=value) |
            Q(admins_user__first_name__icontains=value) |
            Q(admins_user__last_name__icontains=value)
        )