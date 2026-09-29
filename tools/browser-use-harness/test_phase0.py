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


# Lever: a radio/checkbox's `group` is the first option's label (or ''), never the question.
CARD = "cards[001326c7][field{}]"
LEVER = [f(0, "checkbox", name="pronouns", label="He/him"),
         f(1, "checkbox", name="pronouns", label="She/her", group="He/him"),
         f(2, "checkbox", name="pronouns", label="They/them", group="He/him"),
         f(9, "checkbox", id_="customPronounsOption", label="Custom", group="He/him")] + \
        [f(3 + 2 * k + j, "radio", name=CARD.format(k), label=o, group="" if j == 0 else "Yes", required=True)
         for k in (0, 1) for j, o in enumerate(("Yes", "No"))]
LEVER_PLAN = {"fields": [
    {"label": "Pronouns", "widget": "checkbox", "options": ["He/him", "She/her", "They/them", "Custom"],
     "fill_from": "never"},
    {"label": "Are you legally authorized to work in the US?", "widget": "radio", "required": True,
     "options": ["Yes", "No"], "fill_from": "answer_bank_question"},
    {"label": "Do you require sponsorship?", "widget": "radio", "required": True,
     "options": ["Yes", "No"], "fill_from": "answer_bank_question"},
]}

# Ashby: multi-select checkboxes are named per option but share the question as `group`;
# a Yes/No question is one hidden checkbox with no label and the question as `group`.
HEAR = "How did you hear about us?"
ASHBY = [f(0, "checkbox", id_="q-0", name="LinkedIn", label="LinkedIn", group=HEAR),
         f(1, "checkbox", id_="q-1", name="Glassdoor", label="Glassdoor", group=HEAR),
         f(2, "checkbox", name="Prefer not to say", label="Prefer not to say", group=HEAR),
         f(3, "checkbox", name="Prefer not to say", label="Prefer not to say", group="Which communities?"),
         f(4, "checkbox", name="Other", label="Other", group="Which communities?"),
         f(5, "checkbox", name="9fd0020d", group="Are you based in the EU?", visible=False)]
ASHBY_PLAN = {"fields": [
    {"label": "How did you hear about us", "widget": "checkbox", "options": ["LinkedIn", "Glassdoor"]},
    {"label": "Which communities?", "widget": "checkbox", "options": ["Prefer not to say", "Other"]},
    {"label": "Are you based in the EU?", "widget": "checkbox", "options": ["Yes", "No"]},
]}


class ScoreTest(unittest.TestCase):
    def test_lever_groups_matched_by_options(self):
        self.assertEqual([d["options"] for d in dom_fields(LEVER)],
                         [{"he him", "she her", "they them", "custom"}, {"yes", "no"}, {"yes", "no"}])
        s = score(LEVER_PLAN, LEVER)
        self.assertEqual((s["dom_fields"], s["matched"], s["missed"], s["extra"]), (3, 3, [], []))
        self.assertEqual(s["required_acc"], 1.0)

    def test_ashby_groups_by_question(self):
        self.assertEqual([d["label"] for d in dom_fields(ASHBY)], [HEAR, "Which communities?", "Are you based in the EU?"])
        s = score(ASHBY_PLAN, ASHBY)
        self.assertEqual((s["recall"], s["precision"], s["missed"], s["extra"]), (1.0, 1.0, [], []))

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
