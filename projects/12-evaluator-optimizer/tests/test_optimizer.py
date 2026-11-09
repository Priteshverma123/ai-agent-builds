from eval_optimizer import EvaluatorOptimizer, MockLLM, Rubric


def test_loop_reaches_target_and_scores_improve(brief):
    llm = MockLLM()
    result = EvaluatorOptimizer(llm, Rubric(brief, llm)).run(brief)
    totals = [a.evaluation.total for a in result.attempts]
    assert result.stop_reason.startswith("target reached")
    assert totals[0] < 50 <= totals[-1] and totals == sorted(totals)
    assert "revolutionary" not in result.best.text


def test_max_iterations_is_a_hard_budget(brief):
    llm = MockLLM()
    result = EvaluatorOptimizer(llm, Rubric(brief, llm), target=101, max_iterations=2, patience=5).run(brief)
    assert len(result.attempts) == 2 and result.stop_reason.startswith("max iterations")


class StubbornWriter(MockLLM):
    """Ignores feedback: every revision is the same first draft."""

    def complete(self, system, prompt):
        return super().complete(system.replace("TASK: REVISE", "TASK: WRITE"), prompt)


def test_plateau_stops_early_and_keeps_the_best_draft(brief):
    judge = MockLLM()
    result = EvaluatorOptimizer(StubbornWriter(), Rubric(brief, judge), patience=2).run(brief)
    assert result.stop_reason.startswith("plateau")
    assert len(result.attempts) == 3 and result.best.iteration == 1


class RegressingWriter(MockLLM):
    """Revises well once, then starts making things worse."""

    def __init__(self):
        self.revisions = 0

    def complete(self, system, prompt):
        if "TASK: REVISE" in system:
            self.revisions += 1
            if self.revisions > 1:
                return "We built a revolutionary thing and we love it."
        return super().complete(system, prompt)


def test_best_draft_is_returned_even_if_later_revisions_are_worse(brief):
    result = EvaluatorOptimizer(RegressingWriter(), Rubric(brief, MockLLM())).run(brief)
    assert result.best.iteration == 2
    assert all(a.evaluation.total < result.best.evaluation.total for a in result.attempts[2:])
    assert "revolutionary" not in result.best.text
