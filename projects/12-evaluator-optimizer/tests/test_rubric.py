from eval_optimizer import MockLLM, Rubric

GOOD = ("Snapshots saves your whole dev environment in one click. You can restore any snapshot in under "
        "10 seconds, so a broken branch never costs you an afternoon. Snapshots is free on all plans, "
        "including Free. Try it today: run `snap save` in any project and see your setup come back.")


def test_good_text_scores_high(brief):
    evaluation = Rubric(brief, MockLLM()).evaluate(GOOD)
    assert evaluation.total >= 90
    assert evaluation.feedback() == []


def test_checks_name_exactly_what_is_wrong(brief):
    text = "Our revolutionary Snapshots feature is here. We love it."
    feedback = " ".join(Rubric(brief, MockLLM()).evaluate(text).feedback())
    assert "Remove hype phrase 'revolutionary'" in feedback
    assert "Mention '10 seconds'" in feedback and "Mention 'free'" in feedback
    assert "call to action" in feedback


def test_feedback_is_ranked_by_points_lost(brief):
    evaluation = Rubric(brief, MockLLM()).evaluate("Our revolutionary Snapshots feature is here. We love it.")
    top = evaluation.feedback(top=1)[0]
    assert top.startswith("Mention")  # keywords carry the biggest weight (2.0)


class BrokenJudge:
    name = "broken"

    def complete(self, system, prompt):
        return '{"clarity": "great"}'


def test_malformed_judge_output_scores_lowest_instead_of_crashing(brief):
    scores = Rubric(brief, BrokenJudge()).evaluate(GOOD).by_name()
    assert scores["clarity"] == 1 and scores["audience"] == 1
