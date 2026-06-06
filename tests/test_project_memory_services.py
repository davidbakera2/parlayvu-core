import os
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import initialize_database
from app.models import Approval, AgentEvent, Client, GeneratedOutput, Project, TeamsChannelBinding
from app.project_memory import (
    bind_teams_channel,
    get_project_context,
    get_teams_channel_binding,
    list_clients,
    list_projects,
    record_agent_event,
    record_generated_output,
)


RAMAIR_PROJECT_ID = "ramair-straight-from-the-hart"


def _seed_minimal_ramair(session) -> None:
    """Minimal RamAir fixture for the project-memory read tests.

    Replaces the removed app.demo_seed.seed_ramair_demo helper — only seeds the
    rows these tests actually assert on (client, project, one output, one pending
    approval).
    """
    session.add(Client(id="ramair", name="RamAir International"))
    session.add(
        Project(
            id=RAMAIR_PROJECT_ID,
            client_id="ramair",
            name="Straight from the Hart Content Engine",
        )
    )
    output = GeneratedOutput(
        project_id=RAMAIR_PROJECT_ID,
        agent_name="dylan",
        output_type="astro_site",
        title="Campaign landing page",
        status="generated",
    )
    session.add(output)
    session.add(
        Approval(
            project_id=RAMAIR_PROJECT_ID,
            requested_by_agent="dylan",
            status="pending",
        )
    )


class ProjectMemoryServiceTests(unittest.TestCase):
    def test_memory_writes_are_disabled_by_default(self):
        with patch.dict(os.environ, {"PROJECT_MEMORY_ENABLED": "false"}):
            output_id = record_generated_output(
                client_id="ramair",
                agent_name="dylan",
                output_type="astro_site",
                title="Landing page",
            )

        self.assertIsNone(output_id)

    def test_records_output_and_event_when_enabled(self):
        engine = create_engine("sqlite:///:memory:")
        initialize_database(engine)
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        def fake_scope():
            class Scope:
                def __enter__(self):
                    self.session = Session()
                    return self.session

                def __exit__(self, exc_type, exc, traceback):
                    if exc_type:
                        self.session.rollback()
                    else:
                        self.session.commit()
                    self.session.close()

            return Scope()

        with patch.dict(os.environ, {"PROJECT_MEMORY_ENABLED": "true"}):
            with patch("app.project_memory.session_scope", fake_scope):
                output_id = record_generated_output(
                    client_id="ramair",
                    project_id="straight-from-the-hart",
                    project_name="Straight from the Hart",
                    agent_name="dylan",
                    output_type="astro_site",
                    title="Campaign landing page",
                    status="generated",
                )
                event_id = record_agent_event(
                    client_id="ramair",
                    project_id="straight-from-the-hart",
                    project_name="Straight from the Hart",
                    agent_name="dylan",
                    event_type="site_generated",
                    channel="api",
                )

        with Session() as session:
            self.assertIsNotNone(output_id)
            self.assertIsNotNone(event_id)
            self.assertIsNotNone(session.get(Project, "straight-from-the-hart"))
            self.assertEqual(session.query(GeneratedOutput).count(), 1)
            self.assertEqual(session.query(AgentEvent).count(), 1)

    def test_reads_seeded_project_context(self):
        engine = create_engine("sqlite:///:memory:")
        initialize_database(engine)
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        with Session() as session:
            _seed_minimal_ramair(session)
            session.commit()

        def fake_scope():
            class Scope:
                def __enter__(self):
                    self.session = Session()
                    return self.session

                def __exit__(self, exc_type, exc, traceback):
                    if exc_type:
                        self.session.rollback()
                    else:
                        self.session.commit()
                    self.session.close()

            return Scope()

        with patch("app.project_memory.session_scope", fake_scope):
            clients = list_clients()
            projects = list_projects(client_id="ramair")
            context = get_project_context(RAMAIR_PROJECT_ID)

        self.assertEqual(clients[0]["id"], "ramair")
        self.assertEqual(projects[0]["id"], RAMAIR_PROJECT_ID)
        self.assertEqual(context["client"]["name"], "RamAir International")
        self.assertEqual(context["approvals"][0]["status"], "pending")

    def test_binds_teams_channel_to_project(self):
        engine = create_engine("sqlite:///:memory:")
        initialize_database(engine)
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        with Session() as session:
            _seed_minimal_ramair(session)
            session.commit()

        def fake_scope():
            class Scope:
                def __enter__(self):
                    self.session = Session()
                    return self.session

                def __exit__(self, exc_type, exc, traceback):
                    if exc_type:
                        self.session.rollback()
                    else:
                        self.session.commit()
                    self.session.close()

            return Scope()

        with patch("app.project_memory.session_scope", fake_scope):
            binding = bind_teams_channel(
                team_id="team-1",
                channel_id="channel-1",
                channel_name="RamAir",
                client_id="ramair",
                project_id=RAMAIR_PROJECT_ID,
                project_name="Straight from the Hart Content Engine",
                bound_by="dave@parlayvu.ai",
            )
            loaded = get_teams_channel_binding(team_id="team-1", channel_id="channel-1")

        self.assertEqual(binding["project_id"], RAMAIR_PROJECT_ID)
        self.assertEqual(loaded["client_id"], "ramair")
        self.assertEqual(loaded["channel_name"], "RamAir")

        with Session() as session:
            self.assertEqual(session.query(TeamsChannelBinding).count(), 1)


if __name__ == "__main__":
    unittest.main()
