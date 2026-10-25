"""Explicit Indian catalog provisioning; existing rows and edits are retained."""
from .database import Database
from .demo import populate_workspace


def seed_inventory(database_path, workspace_id=1):
    database = Database(database_path)
    with database.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        workspace = db.execute('SELECT demo_seeded FROM workspaces WHERE id=?', (workspace_id,)).fetchone()
        if workspace is None:
            raise ValueError('Workspace not found')
        if workspace['demo_seeded']:
            return 0
        count = populate_workspace(db, workspace_id)
        db.execute('UPDATE workspaces SET demo_seeded=1 WHERE id=?', (workspace_id,))
        return count


if __name__ == '__main__':
    from .main import production_app
    app = production_app()
    print('Private workspaces provisioned. Existing inventory and edits were preserved.')
