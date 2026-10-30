-- Run once as a metastore / catalog admin. Replace <principal> with the app's service principal
-- (Apps > your app > Authorization shows its application id) and the job's run-as identity.
-- The app and job need NO personal tokens: they use these grants.

GRANT USE CATALOG ON CATALOG main TO `<principal>`;
GRANT USE SCHEMA, CREATE TABLE, CREATE VOLUME ON SCHEMA main.pipeline_template TO `<principal>`;
GRANT SELECT, MODIFY ON SCHEMA main.pipeline_template TO `<principal>`;
GRANT READ VOLUME, WRITE VOLUME ON VOLUME main.pipeline_template.documents TO `<principal>`;

-- Also give the principal, in the workspace UI:
--   CAN USE on the SQL warehouse
--   CAN QUERY on the model serving endpoint (LLM_ENDPOINT)
