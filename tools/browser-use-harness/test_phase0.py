"""Offline check of phase0.score: a fake plan against a fake DOM snapshot (SNAPSHOT_JS shape)."""

import unittest

from phase0 import dom_fields, score


def f(i, type_="text", id_="", name="", label="", group="", required=False, visible=True, role=""):
    return {"index": i, "type": type_, "role": role, "id": id_, "name": name, "label": label, "group": group,
            "required": required, "value": "", "display": "", "visible": visible, "mark": ""}


SNAP = [
    f(0, id_="first_name", label="First Name*", required=True),
    f(1, "email", id_="email", label="Email*", required=True),
    f(2, "file", id_="resume", label="Resume/CV", required=True, visible=False),   # styled, hidden input
    f(3, id_="country", role="combobox", label="Country*", required=True),
    f(4, group="Country*", required=True),                  # react-select's required twin: no id/name/label
    f(5, "select", id_="question_1", label="Will you require sponsorship?"),
    f(6, "radio", id_="r1", name="gender", group="Gender", label="Male"),
    f(7, "radio", id_="r2", name="gender", group="Gender", label="Female"),
    f(8, "checkbox", id_="c1", name="consent", label="I agree to the privacy policy", required=True),
    f(9, "textarea", id_="g-recaptcha-response", visible=False),                  # hidden: not a field
]

PLAN = {"fields": [
    {"label": "First Name", "selector_hint": "#first_name", "widget": "text", "required": True,
     "options": [], "fill_from": "given_name"},
    {"label": "Email", "selector_hint": "email", "widget": "text", "required": False,        # required wrong
     "options": [], "fill_from": "email"},
    {"label": "Resume/CV", "selector_hint": "", "widget": "file", "required": True,           # matched by label
     "options": [], "fill_from": "resume"},
    {"label": "Country", "selector_hint": "country", "widget": "react_select", "required": True,
     "options": ["United States", "Canada"], "fill_from": "country_code"},
    {"label": "Will you require sponsorship?", "selector_hint": "question_1", "widget": "text",  # widget wrong
     "required": False, "options": [], "fill_from": "answer_bank_question"},                    # no options
    {"label": "Gender", "selector_hint": "r2", "widget": "radio", "required": False,
     "options": ["Male", "Female"], "fill_from": "unknown"},                                   # must be never
    {"label": "Favourite colour", "selector_hint": "colour", "widget": "text", "required": False,  # invented
     "options": [], "fill_from": "unknown"},
]}


class ScoreTest(unittest.TestCase):
    def test_dom_fields_groups_radios_drops_hidden_and_twins(self):
        labels = [d["label"] for d in dom_fields(SNAP)]
        self.assertEqual(labels, ["First Name*", "Email*", "Resume/CV", "Country*", "Will you require sponsorship?",
                                  "Gender", "I agree to the privacy policy"])

    def test_score(self):
        s = score(PLAN, SNAP)
        self.assertEqual((s["dom_fields"], s["plan_fields"], s["matched"]), (7, 7, 6))
        self.assertAlmostEqual(s["recall"], 6 / 7)
        self.assertAlmostEqual(s["precision"], 6 / 7)
        self.assertAlmostEqual(s["required_acc"], 5 / 6)
        self.assertEqual((s["options_ok"], s["options_total"]), (1, 2))       # country yes, sponsorship no
        self.assertAlmostEqual(s["widget_acc"], 5 / 6)
        self.assertEqual((s["sensitive_never"], s["sensitive_total"]), (0, 2))  # gender unknown, consent missed
        self.assertEqual(s["missed"], ["I agree to the privacy policy"])
        self.assertEqual(s["extra"], ["Favourite colour"])
        self.assertEqual(s["sensitive_violations"], ["Gender"])

    def test_empty_plan(self):
        s = score({"fields": []}, SNAP)
        self.assertEqual((s["recall"], s["precision"], s["matched"]), (0.0, 0.0, 0))


if __name__ == "__main__":
    unittest.main()
