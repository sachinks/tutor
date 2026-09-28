"""Shared test helpers. Imported by tests only."""

from django.db import connection
from django.test.utils import CaptureQueriesContext


class QueryBudgetMixin:
    """Guards against N+1 queries (quality backlog Q2).

    ``assertQueriesDoNotGrow`` calls an endpoint once to warm it up (first-time writes such as
    "lesson opened" are excluded), counts the queries of a second call, adds more rows with ``grow``,
    and checks that a third call runs exactly as many queries, and no more than ``budget``.
    """

    def count_queries(self, call):
        with CaptureQueriesContext(connection) as ctx:
            response = call()
        return len(ctx.captured_queries), response, ctx.captured_queries

    def assertQueriesDoNotGrow(self, call, grow, budget, expected_status=200):
        response = call()
        self.assertEqual(response.status_code, expected_status, response.content)
        before, response, _ = self.count_queries(call)
        self.assertEqual(response.status_code, expected_status, response.content)
        grow()
        after, response, queries = self.count_queries(call)
        self.assertEqual(response.status_code, expected_status, response.content)
        sql = "\n".join(q["sql"] for q in queries)
        self.assertEqual(before, after, f"Query count grew from {before} to {after} with more rows:\n{sql}")
        self.assertLessEqual(after, budget, f"{after} queries is over the budget of {budget}:\n{sql}")
        return response
