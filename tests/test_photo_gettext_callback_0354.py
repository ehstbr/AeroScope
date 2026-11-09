"""Regressions: GTK callback arguments must not shadow GNU Gettext `_()`."""
import ast
from pathlib import Path
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1] / 'aeroscope'


def _gettext_calls(expression):
    return [
        node for node in ast.walk(expression)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == '_'
    ]


def test_gtk_callbacks_do_not_shadow_gettext_in_any_module():
    for path in SOURCE.rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Lambda) and _gettext_calls(node.body):
                arguments = node.args
                names = {arg.arg for arg in (*arguments.posonlyargs, *arguments.args,
                                             *arguments.kwonlyargs)}
                names.update(arg.arg for arg in (arguments.vararg, arguments.kwarg) if arg)
                assert '_' not in names, (path.name, node.lineno)


def test_photo_callbacks_invoke_translation_when_clicked():
    tree = ast.parse((SOURCE / 'ui.py').read_text(encoding='utf-8'))
    callbacks = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Lambda) and node.args.vararg:
            text = ast.unparse(node.body)
            for key in ('Original photo', 'Photo gallery · '):
                if f"_('{key}')" in text and 'self._view_website(' in text:
                    callbacks[key] = node
    assert set(callbacks) == {'Original photo', 'Photo gallery · '}
    opened = []
    receiver = SimpleNamespace(_view_website=lambda url, title: opened.append((url, title)))
    variables = {'self': receiver,
                 '_': lambda msg: 'PT: ' + msg,
                 'gallery_url': 'https://example.test/gallery',
                 'registration': 'PT-ABC',
                 'photo': {'link': 'https://example.test/photo'}}
    for key in ('Photo gallery · ', 'Original photo'):
        callback = callbacks[key]
        fn = eval(compile(ast.Expression(callback), '<photo callback>', 'eval'), variables)
        fn(object())  # Gtk passes the clicked widget as an argument
    assert opened == [
        ('https://example.test/gallery', 'PT: Photo gallery · PT-ABC'),
        ('https://example.test/photo', 'PT: Original photo'),
    ]
