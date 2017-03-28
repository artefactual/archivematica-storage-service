
try:
    from functools import wraps
except ImportError:
    from django.utils.functional import wraps

from django.shortcuts import render_to_response
from django.template import RequestContext


# Requires confirmation from a prompt page before executing a request
# (see http://djangosnippets.org/snippets/1922/)
def confirm_required(template_name, context_creator, key='__confirm__'):
    """
    Decorator for views that need confirmation page. For example, delete
    object view. Decorated view renders confirmation page defined by template
    'template_name'. If request.POST contains confirmation key, defined
    by 'key' parameter, then original view is executed.

    Context for confirmation page is created by function 'context_creator',
    which accepts same arguments as decorated view.

    Example:
        def remove_file_context(request, id):
            file = get_object_or_404(Attachment, id=id)
            return RequestContext(request, {'file': file})

        @confirm_required('remove_file_confirm.html', remove_file_context)
        def remove_file_view(request, id):
            file = get_object_or_404(Attachment, id=id)
            file.delete()
            next_url = request.GET.get('next', '/')
            return HttpResponseRedirect(next_url)

    Example of HTML template:
        <h1>Remove file {{ file }}?</h1>
        <form method="POST" action="">
            <input type="hidden" name="__confirm__" value="1" />
            <input type="submit" value="delete"/> <a href="{{ file.get_absolute_url }}">cancel</a>
        </form>

    """
    def decorator(func):
        def inner(request, *args, **kwargs):
            if key in request.POST:
                return func(request, *args, **kwargs)
            else:
                context = context_creator and context_creator(request, *args, **kwargs) \
                    or RequestContext(request)
                return render_to_response(template_name, context)
        return wraps(func)(inner)
    return decorator
