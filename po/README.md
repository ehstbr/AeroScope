# AeroScope translations

- Native language: English (United States), stored in Python Gettext `msgid` values.
- Template: `aeroscope.pot` (the original English reference for new locales).
- First translation: `pt_BR.po` (Brazilian Portuguese, migrated from the 0.3.49 source).
- Optional reference: `en_US.po` (English identity catalog for reviewers).
- Active compiled catalog: `aeroscope/locale/pt_BR/LC_MESSAGES/aeroscope.mo`.

The default is **Automatic (system)**, using the Ubuntu/GNOME locale when it
is supported (pt_BR or en_US), with native English as the fallback. Users can
select automatic, English or Brazilian Portuguese in **Preferences → Appearance
→ Language** and restart the application. Existing 0.3.50 implicit English
settings migrate automatically. To force English, select it explicitly.
The setting is stored at `$XDG_CONFIG_HOME/aeroscope/settings.json` (or under
`~/.config/aeroscope/`). For testing, set `AEROSCOPE_LANGUAGE=pt_BR`.

To refresh the template after adding `_('English message')` markers:

```sh
# Ubuntu/Debian: sudo apt install gettext
find aeroscope -name '*.py' -print0 | xargs -0 xgettext --language=Python --from-code=UTF-8 --keyword=_ --keyword=ngettext:1,2 --output=po/aeroscope.pot --package-name=AeroScope
msgmerge --update po/pt_BR.po po/aeroscope.pot
msgfmt --check --output-file=aeroscope/locale/pt_BR/LC_MESSAGES/aeroscope.mo po/pt_BR.po
```

For additional languages, copy the POT with `msginit --locale=xx_YY`, add the
locale to `po/LINGUAS`, compile the new `.po` to `.mo`, and add the locale to
`SUPPORTED_LANGUAGES` in `aeroscope/i18n.py` and the Preferences combo.
Maintain source-text placeholders (`{value0}` and `%s`) in each translation.
ICAO, METAR and SIGMET protocol codes are intentionally not translated.
Avoid translating strings that serve as settings keys, icons or API payloads.
