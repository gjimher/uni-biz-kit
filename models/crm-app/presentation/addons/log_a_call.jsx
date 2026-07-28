// "Log a call" — the quick action a rep uses twenty times a day: record that a
// conversation happened without leaving the list. It writes a completed activity of
// type 'call', linked to the row it was launched from, owned by the signed-in user.
//
// Only the affordance lives here: the insert goes through the data provider, so
// row-level security decides whether it is allowed, exactly as in a form.
import React from 'react';
import PhoneInTalkIcon from '@mui/icons-material/PhoneInTalk';
import { Button, Dialog, DialogActions, DialogContent, DialogTitle, TextField } from '@mui/material';
import { getProfile } from '../lib';

export const Icon = PhoneInTalkIcon;
export const tooltip = 'Log a call';

// The button only appears where the user may actually create the activity.
export const visible = ({ permissions }) => Boolean(
  permissions?.activity?.includes('write') || permissions?.['*']?.includes('write'),
);

export const execute = ({ resource, record, dataProvider, notify, refresh, close }) => (
  <LogCallDialog
    resource={resource}
    record={record}
    dataProvider={dataProvider}
    notify={notify}
    refresh={refresh}
    close={close}
  />
);

const today = () => new Date().toISOString().slice(0, 10);

function LogCallDialog({ resource, record, dataProvider, notify, refresh, close }) {
  const label = record?.id_presentation || `#${record?.id}`;
  const [subject, setSubject] = React.useState(`Call with ${label}`);
  const [minutes, setMinutes] = React.useState('15');
  const [notes, setNotes] = React.useState('');
  const [saving, setSaving] = React.useState(false);

  const save = async () => {
    setSaving(true);
    try {
      const profile = await getProfile();
      // The activity hangs from whatever the list was showing: a contact call also
      // belongs to that contact's account, so the timeline reads the same from both.
      const links = { contact: null, account: null, opportunity: null, lead: null };
      if (resource === 'contact') {
        links.contact = record.id;
        links.account = record.account ?? null;
      } else if (resource === 'opportunity') {
        links.opportunity = record.id;
        links.account = record.account ?? null;
        links.contact = record.primary_contact ?? null;
      } else if (resource === 'lead') {
        links.lead = record.id;
      } else if (resource === 'account') {
        links.account = record.id;
      }

      await dataProvider.create('activity', {
        data: {
          subject,
          type: 'call',
          status: 'completed',
          priority: 'normal',
          due_date: today(),
          completed_date: today(),
          duration_minutes: Number(minutes) || null,
          owner: profile?.record?.id ?? null,
          description: notes || null,
          ...links,
        },
      });
      notify('Call logged', { type: 'info' });
      refresh();
      close();
    } catch (error) {
      notify(error.message || 'Could not log the call', { type: 'warning' });
      setSaving(false);
    }
  };

  return (
    <Dialog open onClose={close} fullWidth maxWidth="sm">
      <DialogTitle>Log a call</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 1 }}>
        <TextField label="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} fullWidth autoFocus />
        <TextField label="Duration (minutes)" value={minutes} onChange={(e) => setMinutes(e.target.value)} type="number" />
        <TextField label="What was said" value={notes} onChange={(e) => setNotes(e.target.value)} multiline minRows={3} fullWidth />
      </DialogContent>
      <DialogActions>
        <Button onClick={close} disabled={saving}>Cancel</Button>
        <Button onClick={save} variant="contained" disabled={saving || !subject.trim()}>Log call</Button>
      </DialogActions>
    </Dialog>
  );
}
