_AUTH_IMPORT = "import { Title, useAuthenticated } from 'react-admin';"
_PLAIN_IMPORT = "import { Title } from 'react-admin';"

# Without an authProvider there is no session to check (and useAuthenticated
# would have nothing to call), so the guard is only generated with one.
_AUTH_GUARD = """  // The pages describe the whole model, so they are for signed-in users only:
  // this bounces visitors without a session to the app's sign-in page.
  useAuthenticated();
"""


def generate(has_auth_provider: bool) -> str:
    return _TEMPLATE.replace(
        "__REACT_ADMIN_IMPORT__", _AUTH_IMPORT if has_auth_provider else _PLAIN_IMPORT
    ).replace(
        "__AUTH_GUARD__", _AUTH_GUARD if has_auth_provider else ""
    )


_TEMPLATE = r"""import * as React from 'react';
import { useParams } from 'react-router-dom';
__REACT_ADMIN_IMPORT__
import {
  Accordion, AccordionDetails, AccordionSummary, Box, Card, CardContent, Chip,
  Dialog, DialogContent, DialogTitle, MenuItem, Stack, Table, TableBody, TableCell,
  TableHead, TableRow, TextField, Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { docsModel } from './docsModel';

// Model documentation, rendered from docsModel.js — the enriched model the
// generators consume. Everything shown here (concepts, fields, roles,
// permissions) is generated data: there is nothing to fetch and nothing to save.

const conceptByName = Object.fromEntries(docsModel.concepts.map((concept) => [concept.name, concept]));

const ACCESS_COLORS = { read: 'info', write: 'success', owner_write: 'warning' };

const AccessChip = ({ access }) => (
  <Chip
    size="small"
    label={access}
    color={ACCESS_COLORS[access] || 'default'}
    variant={access === 'none' ? 'outlined' : 'filled'}
  />
);

const Mono = ({ children }) => (
  <Box component="span" sx={{ fontFamily: 'monospace' }}>{children}</Box>
);

const Section = ({ title, subtitle, children }) => (
  <Card sx={{ mt: 1 }}>
    <CardContent>
      <Typography variant="h6">{title}</Typography>
      {subtitle && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{subtitle}</Typography>
      )}
      {children}
    </CardContent>
  </Card>
);

const RolesDoc = () => (
  <Section
    title="Roles"
    subtitle="Roles the model defines. A profile concept links each signed-in user to one of its rows."
  >
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>Role</TableCell>
          <TableCell>Description</TableCell>
          <TableCell>Profile concept</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {docsModel.roles.map((role) => (
          <TableRow key={role.name}>
            <TableCell><Mono>{role.name}</Mono></TableCell>
            <TableCell>{role.description}</TableCell>
            <TableCell>{role.profileConcept ? <Mono>{role.profileConcept}</Mono> : '—'}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  </Section>
);

const typeLabel = (field) => {
  let label = field.type;
  if (field.subtype) label += ` (${field.subtype})`;
  if (field.target) label += ` → ${field.target}`;
  return label;
};

const requiredLabel = (required) => {
  if (required === true) return 'yes';
  if (required === false) return '—';
  return required; // 'ask_after_login': collected by the post-login profile dialog
};

const FieldTable = ({ fields }) => (
  <Table size="small">
    <TableHead>
      <TableRow>
        <TableCell>Field</TableCell>
        <TableCell>Type</TableCell>
        <TableCell>Required</TableCell>
        <TableCell>Description</TableCell>
      </TableRow>
    </TableHead>
    <TableBody>
      {fields.map((field) => (
        <TableRow key={field.name}>
          <TableCell>
            <Mono>{field.name}</Mono>
            {field.unique && <Chip size="small" label="unique" sx={{ ml: 1 }} />}
          </TableCell>
          <TableCell>
            <Mono>{typeLabel(field)}</Mono>
            {field.enumValues && (
              <Typography variant="caption" display="block" color="text.secondary">
                {field.enumValues.join(' · ')}
              </Typography>
            )}
            {field.constraints.length > 0 && (
              <Typography variant="caption" display="block" color="text.secondary">
                {field.constraints.join(', ')}
              </Typography>
            )}
            {field.visibility !== 'editable' && (
              <Typography variant="caption" display="block" color="text.secondary">
                {field.visibility}
              </Typography>
            )}
          </TableCell>
          <TableCell>{requiredLabel(field.required)}</TableCell>
          <TableCell>{field.description}</TableCell>
        </TableRow>
      ))}
    </TableBody>
  </Table>
);

const ConceptsDoc = () => {
  const [search, setSearch] = React.useState('');
  const needle = search.trim().toLowerCase();
  const concepts = docsModel.concepts.filter((concept) => (
    !needle
    || concept.name.includes(needle)
    || (concept.menuLabel || '').toLowerCase().includes(needle)
    || concept.description.toLowerCase().includes(needle)
    || concept.fields.some((field) => field.name.includes(needle))
  ));

  return (
    <Section
      title="Concepts"
      subtitle="Every concept the app runs on, including the ones the generator injects (names starting with '_')."
    >
      <TextField
        size="small"
        label="Filter"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        sx={{ mb: 2 }}
      />
      {concepts.map((concept) => (
        <Accordion key={concept.name} disableGutters>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
              <Typography><Mono>{concept.name}</Mono></Typography>
              {concept.menuLabel && (
                <Typography variant="body2" color="text.secondary">{concept.menuLabel}</Typography>
              )}
              {concept.generated && <Chip size="small" label="generated" />}
              {concept.storage === 'view' && <Chip size="small" label="view" />}
              {concept.archetype !== 'root' && <Chip size="small" label={concept.archetype} />}
              {concept.workflow && <Chip size="small" label={'workflow: ' + concept.workflow} />}
              {concept.versioned && <Chip size="small" label="versioned" />}
            </Stack>
          </AccordionSummary>
          <AccordionDetails>
            {concept.description && (
              <Typography variant="body2" sx={{ mb: 2 }}>{concept.description}</Typography>
            )}
            <FieldTable fields={concept.fields} />
          </AccordionDetails>
        </Accordion>
      ))}
      {concepts.length === 0 && (
        <Typography variant="body2" color="text.secondary">No concept matches the filter.</Typography>
      )}
    </Section>
  );
};

const WorkflowsDoc = () => (
  <Section
    title="Workflows"
    subtitle="State machines the backend enforces. The task owner is the user responsible for a record while it sits in its current state: assigners are the roles that can change it, and entering a state clears it back to the assignable pool unless the state keeps it."
  >
    {docsModel.workflows.length === 0 && (
      <Typography variant="body2" color="text.secondary">This model defines no workflows.</Typography>
    )}
    {docsModel.workflows.map((workflow) => (
      <Box key={workflow.name} sx={{ mb: 3 }}>
        <Typography variant="subtitle1"><Mono>{workflow.name}</Mono></Typography>
        {workflow.description && (
          <Typography variant="body2" color="text.secondary">{workflow.description}</Typography>
        )}
        <Typography variant="caption" color="text.secondary">
          Concepts: <Mono>{workflow.concepts}</Mono>
        </Typography>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>State</TableCell>
              <TableCell>Owners</TableCell>
              <TableCell>Assigners</TableCell>
              <TableCell>Task owner on state entry</TableCell>
              <TableCell>Description</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {workflow.states.map((state) => (
              <TableRow key={state.name}>
                <TableCell><Mono>{state.name}</Mono></TableCell>
                <TableCell>{state.owners.join(', ') || '—'}</TableCell>
                <TableCell>{state.assigners.join(', ') || '—'}</TableCell>
                <TableCell>{state.retainTaskOwner ? 'kept' : 'cleared'}</TableCell>
                <TableCell>{state.description}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Box>
    ))}
  </Section>
);

// One row per (concept, role) the effective ACL grants something on. The detail
// dialog is where the field-level rules show: they are what makes two roles with
// the same concept access behave differently.
const FieldAccessDialog = ({ detail, onClose }) => {
  if (!detail) return null;
  const conceptAcl = docsModel.acl[detail.concept];
  const fields = conceptByName[detail.concept].fields;

  return (
    <Dialog open fullWidth maxWidth="md" onClose={onClose}>
      <DialogTitle>
        <Mono>{detail.concept}</Mono>{' · '}<Mono>{detail.role}</Mono>{' '}
        <AccessChip access={detail.access} />
      </DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Access per field for this role. A field marked <em>differs</em> does not follow the
          concept-level access: field rules usually restrict it, and a writable field under
          read access grants an update on that field alone.
        </Typography>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Field</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Access</TableCell>
              <TableCell>Description</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {fields.map((field) => {
              const fieldAcl = conceptAcl.fields[field.name] || {};
              const access = fieldAcl[detail.role] || 'none';
              return (
                <TableRow key={field.name}>
                  <TableCell><Mono>{field.name}</Mono></TableCell>
                  <TableCell><Mono>{typeLabel(field)}</Mono></TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <AccessChip access={access} />
                      {access !== detail.access && <Chip size="small" variant="outlined" label="differs" />}
                    </Stack>
                  </TableCell>
                  <TableCell>{field.description}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </DialogContent>
    </Dialog>
  );
};

const SecurityDoc = () => {
  const [role, setRole] = React.useState('*');
  const [search, setSearch] = React.useState('');
  const [detail, setDetail] = React.useState(null);

  const rows = [];
  Object.entries(docsModel.acl).forEach(([concept, conceptAcl]) => {
    Object.entries(conceptAcl.main).forEach(([roleName, access]) => {
      rows.push({ concept, role: roleName, access });
    });
  });
  const needle = search.trim().toLowerCase();
  const visible = rows.filter((row) => (
    (role === '*' || row.role === role) && (!needle || row.concept.includes(needle))
  ));

  return (
    <Section
      title="Security"
      subtitle="Effective permissions after composing the three rule levels, the generated concepts included. Click a row for the detail per field."
    >
      <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
        <TextField
          select
          size="small"
          label="Role"
          value={role}
          onChange={(event) => setRole(event.target.value)}
          sx={{ minWidth: 160 }}
        >
          <MenuItem value="*">All roles</MenuItem>
          {docsModel.roles.map((item) => (
            <MenuItem key={item.name} value={item.name}>{item.name}</MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          label="Concept"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </Stack>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Concept</TableCell>
            <TableCell>Role</TableCell>
            <TableCell>Access</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {visible.map((row) => (
            <TableRow
              key={row.concept + '/' + row.role}
              hover
              sx={{ cursor: 'pointer' }}
              onClick={() => setDetail(row)}
            >
              <TableCell><Mono>{row.concept}</Mono></TableCell>
              <TableCell><Mono>{row.role}</Mono></TableCell>
              <TableCell><AccessChip access={row.access} /></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {visible.length === 0 && (
        <Typography variant="body2" color="text.secondary">No permission matches the filter.</Typography>
      )}
      <FieldAccessDialog detail={detail} onClose={() => setDetail(null)} />
    </Section>
  );
};

const PAGES = {
  roles: { label: 'Roles', Component: RolesDoc },
  concepts: { label: 'Concepts', Component: ConceptsDoc },
  workflows: { label: 'Workflows', Component: WorkflowsDoc },
  security: { label: 'Security', Component: SecurityDoc },
};

export const DocsPage = () => {
__AUTH_GUARD__  const { page } = useParams();
  const entry = PAGES[page];

  return (
    <>
      <Title title={docsModel.appName + ' — ' + (entry ? entry.label : 'Documentation')} />
      {entry
        ? <entry.Component />
        : (
          <Section title="Documentation">
            <Typography variant="body2" color="text.secondary">Unknown documentation page.</Typography>
          </Section>
        )}
    </>
  );
};
"""
