from .utils import get_user_hash

def user_hash_context(request):
    if request.user.is_authenticated:
        return {'user_hash': get_user_hash(request.user.id)}
    return {'user_hash': ''}