"""The header shows the Relcom ID session on every page; no network or credentials."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]

class HeaderSessionTests(unittest.TestCase):
    def test_every_page_carries_the_account_link_and_the_script_that_reads_the_session(self):
        for page in ROOT.glob('*.html'):
            text=page.read_text()
            if 'class="header-actions"' not in text:continue
            self.assertRegex(text,r'class="header-actions"><a class="source-link" href="https://ipvx\.org/account(\.(en|de|es))?\.html"',page.name)
            self.assertRegex(text,r'src="assets/(?:(?:en|de|es)/)?relcom\.js\?v=',page.name)
    def test_header_reads_only_the_public_session_and_writes_text(self):
        for lang,title in (('','Вход выполнен через Relcom ID'),('en/','Signed in with Relcom ID'),('de/','Angemeldet mit Relcom ID'),('es/','Sesión iniciada con Relcom ID')):
            js=(ROOT/f'assets/{lang}relcom.js').read_text()
            block=js.split("const headerAccount=",1)[1].split("const sessionStatus=",1)[0]
            self.assertIn("request('/auth/session',{credentials:'same-origin'",block)
            self.assertIn('label.textContent=name',block)
            self.assertNotIn('innerHTML',block)
            self.assertIn(title,block)
            # An expired session leaves the sign-in link in place.
            self.assertIn('expiry<=Date.now())return',block)

if __name__=='__main__':unittest.main()
