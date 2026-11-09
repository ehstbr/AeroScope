"""Check D-Bus interface XML without importing GI on a headless CI host."""
import ast
from pathlib import Path
from xml.etree import ElementTree


def test_dbus_interfaces_parse_and_expose_required_methods():
    source=(Path(__file__).resolve().parents[1]/'aeroscope/status_tray.py').read_text()
    module=ast.parse(source)
    strings={}
    for entry in module.body:
        if isinstance(entry,ast.Assign) and len(entry.targets)==1 and isinstance(entry.targets[0],ast.Name):
            if isinstance(entry.value,ast.Constant) and isinstance(entry.value.value,str):
                strings[entry.targets[0].id]=entry.value.value
    for key, interface in [('ITEM_XML','org.kde.StatusNotifierItem'),
                           ('MENU_XML','com.canonical.dbusmenu')]:
        tree=ElementTree.fromstring(strings[key])
        assert tree.find('interface').attrib['name']==interface
        names={x.attrib['name'] for x in tree.find('interface').findall('method')}
        if key=='ITEM_XML':
            assert {'Activate','SecondaryActivate','ContextMenu'} <= names
        else:
            assert {'GetLayout','Event','GetGroupProperties','AboutToShow'} <= names
