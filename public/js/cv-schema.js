// Shape of the CV. The admin editor draws its form from this; the server checks saves against it.
// Field types: text (one line), long (paragraph), url, lines (list of strings, one per line), list (list of objects).

const t = (key, label, extra = {}) => ({ key, label, type: 'text', ...extra });
const long = (key, label, extra = {}) => ({ key, label, type: 'long', ...extra });

export const CV_SCHEMA = [
  { key: 'person', label: 'Contact', type: 'object', fields: [
    t('name', 'Name'), t('location', 'Based in'), t('email', 'Email'),
    { key: 'links', label: 'Links', type: 'list', item: 'text', fields: [t('label', 'Label'), t('text', 'Shown as'), { key: 'href', label: 'Address', type: 'url' }] },
  ] },
  { key: 'hero', label: 'Hero blurbs', type: 'object', fields: [long('marius', 'Marius (left)'), long('toma', 'Toma (right)')] },
  { key: 'profile', label: 'Profile', type: 'lines', hint: 'One paragraph per line. The first is the big lead.' },
  { key: 'experience', label: 'Experience', type: 'list', item: 'org', fields: [
    t('when', 'When'), t('role', 'Role'), t('org', 'Company'), t('note', 'Note', { hint: 'Optional, e.g. "Full-time, Arad"' }),
    { key: 'points', label: 'Points', type: 'lines', hint: 'One per line.' },
    long('tech', 'Worked with', { hint: 'Optional. Shown as "Worked with …."' }),
  ] },
  { key: 'liveProjects', label: 'Live projects', type: 'list', item: 'name', fields: [
    t('name', 'Name'), t('domain', 'Shown domain'), { key: 'href', label: 'Address', type: 'url' }, long('what', 'What it is'),
  ] },
  { key: 'privateProjects', label: 'Running inside companies', type: 'list', item: 'name', fields: [t('name', 'Name'), long('what', 'What it is')] },
  { key: 'education', label: 'Education', type: 'list', item: 'what', fields: [t('what', 'Degree or course'), t('where', 'Where'), t('when', 'When')] },
  { key: 'skills', label: 'Skills', type: 'list', item: 'group', fields: [t('group', 'Group'), long('items', 'Skills')] },
  { key: 'languages', label: 'Languages', type: 'list', item: 'name', fields: [t('name', 'Language'), t('level', 'Level')] },
  { key: 'awards', label: 'Activities and awards', type: 'list', item: 'what', fields: [t('what', 'Title'), long('detail', 'Detail')] },
  { key: 'interests', label: 'Interests', type: 'long' },
];
