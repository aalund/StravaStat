import unittest
from email.message import EmailMessage

from stravastat.email import build_message, parse_port, subject_for


class TestParsePort(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(parse_port(None), 465)
        self.assertEqual(parse_port(""), 465)
        self.assertEqual(parse_port("junk"), 465)

    def test_valid_values(self):
        self.assertEqual(parse_port("465"), 465)
        self.assertEqual(parse_port("25"), 25)
        self.assertEqual(parse_port(587), 587)


class TestBuildMessage(unittest.TestCase):
    def test_headers_and_body(self):
        message = build_message("Emne", "Broedtekst", "to@example.com", "from@example.com")
        self.assertIsInstance(message, EmailMessage)
        self.assertEqual(message["Subject"], "Emne")
        self.assertEqual(message["To"], "to@example.com")
        self.assertEqual(message["From"], "from@example.com")
        self.assertIn("Broedtekst", message.get_content())

    def test_from_defaults_to_recipient(self):
        message = build_message("Emne", "Krop", "to@example.com")
        self.assertEqual(message["From"], "to@example.com")


class TestSubjectFor(unittest.TestCase):
    def test_with_recommendation(self):
        subject = subject_for({"recommended_ftp_watts": 235})
        self.assertEqual(subject, "StravaStat: anbefalet FTP 235 W")

    def test_without_recommendation(self):
        subject = subject_for({"recommended_ftp_watts": None})
        self.assertEqual(subject, "StravaStat: ingen FTP-anbefaling denne uge")


if __name__ == "__main__":
    unittest.main()
