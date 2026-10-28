"""Localization preserves evidence, attribution, safe links and canonical IDs."""
import unittest
from build_languages import Tree, render, localized, translator
from i18n_sources import Sources, editorial, key


class Languages(unittest.TestCase):
    def catalog(self, source):
        result = {}
        parser = Sources(lambda text, _: result.update({key(text): 'Translated '+text.strip()}) if editorial(text) else None)
        parser.feed(source)
        return result

    def test_missing_translation_is_not_silently_russian(self):
        with self.assertRaises(ValueError):
            translator({})('Подпись проверена')

    def test_evidence_bytes_and_svg_attribute_case(self):
        source = '<!doctype html><html lang="ru"><head><title>Сеть</title></head><body><header></header><main><h1>Пакет</h1><pre>{"подпись":"abc"}</pre><svg viewBox="0 0 20 20"><text x="1">Узел</text></svg></main></body></html>'
        output = render(localized(Tree(source).root, 'index.html', 'de', self.catalog(source), {'index.html': source}))
        self.assertIn('lang="de"', output)
        self.assertIn('<pre>{"подпись":"abc"}</pre>', output)
        self.assertIn('viewBox="0 0 20 20"', output)
        self.assertIn('Translated Узел', output)
        self.assertIn('href="index.es.html"', output)
        self.assertIn('hreflang="de"', output)

    def test_rfc_and_history_originals_keep_authorship_without_duplicate_ids(self):
        source = '<html><head><title>История</title></head><body><header></header><main><h1>Журнал</h1><details class="history-entry" id="HX-0001"><summary>Первый опыт</summary><p>Автор: A</p><p>Ошибка сохранена.</p></details><article class="rfc-prose"><h2 id="scope">Scope</h2><p>Draft proposal.</p></article><a href="account.html#rights">Вход</a><a href="https://ipvx.org/auth/login?returnTo=/account.html">Войти</a></main></body></html>'
        pages = {'history.html': source, 'account.html': 'account'}
        output = render(localized(Tree(source).root, 'history.html', 'en', self.catalog(source), pages))
        self.assertEqual(output.count('id="HX-0001"'), 1)
        self.assertEqual(output.count('id="scope"'), 1)
        self.assertIn('Original record', output)
        self.assertIn('Original document', output)
        self.assertIn('lang="ru"', output)
        self.assertIn('href="account.en.html#rights"', output)
        self.assertIn('returnTo=/account.en.html', output)
        self.assertIn('<p>Ошибка сохранена.</p>', output)
        self.assertIn('<p>Draft proposal.</p>', output)

    def test_translation_markup_is_text(self):
        source = '<html><head><title>Тест</title></head><body><header></header><main><h1>Тест</h1></main></body></html>'
        output = render(localized(Tree(source).root, 'index.html', 'es', {key('Тест'): '<script>bad()</script>'}, {'index.html': source}))
        self.assertIn('&lt;script&gt;bad()&lt;/script&gt;', output)
        self.assertNotIn('<script>bad()', output)


if __name__ == '__main__':
    unittest.main()
