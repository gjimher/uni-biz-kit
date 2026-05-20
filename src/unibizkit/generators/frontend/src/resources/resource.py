import json
from typing import Any, Dict, List
from ...context import Context
from .helpers import (
    find_owned_children,
    find_many_to_many_links,
    collect_all_descendants,
    get_optimized_react_admin_imports,
    generate_field_components,
)


def _generate_document_tab(concept_name: str, docs: Dict[str, Any], has_workflow: bool = False) -> str:
    tags_js = ", ".join(f"'{t}'" for t in docs["tags"])
    versioned_js = "true" if docs["versioned"] else "false"
    can_edit_prop = " canEditParent={canEdit}" if has_workflow else ""
    return f"""
      <FormTab label="Documents">
        <DocumentTab conceptName="{concept_name}" tags={{[{tags_js}]}} versioned={{{versioned_js}}}{can_edit_prop} />
      </FormTab>"""


def _validations_for_concept(ctx: Context, concept: Dict[str, Any]) -> List[Dict[str, Any]]:
    concept_name = concept["name"]
    return [
        validation for validation in ctx.validations_config.get("validations", [])
        if validation["concept"] == concept_name
    ]


def _has_validations(ctx: Context, concept: Dict[str, Any]) -> bool:
    return bool(_validations_for_concept(ctx, concept))


def _generate_recursive_dialogs(
    ctx: Context,
    concept: Dict[str, Any],
    parent_name: str,
    visited=None
) -> List[str]:
    if visited is None:
        visited = set()
    resource_name = concept["name"]

    state_key = (resource_name, parent_name)
    if state_key in visited:
        return []
    visited.add(state_key)

    components = []

    my_children = find_owned_children(resource_name, ctx.concepts)

    for child_info in my_children:
        if child_info["concept"]["name"] == resource_name:
            continue
        components.extend(_generate_recursive_dialogs(ctx, child_info["concept"], resource_name, visited))

    title_desc_prop = f' description="{concept["description"].replace(chr(34), "&quot;")}"' if concept["description"] else ''

    fk_field_name = ""
    for field in concept["fields"]:
        if field["type"] == "relation_to_one" and field["target"] == parent_name:
            fk_field_name = field["name"]
            break

    fields_res = generate_field_components(
        concept,
        ctx.concepts,
        ctx.concept_map,
        ctx.presentation_config,
        ctx.security_config,
        owned_children=my_children,
        exclude_fields=[fk_field_name]
    )

    create_fields = fields_res["create_fields"]
    edit_fields = fields_res["edit_fields"]
    child_tabs = fields_res["child_tabs"]

    workflow_ui = ""
    concept_workflow = ctx.business_schema.get("_concept_workflow", {}).get(resource_name)
    if concept_workflow:
        wf_json = json.dumps(concept_workflow)
        workflow_ui = f'<WorkflowSelector workflow={{{wf_json}}} resource="{resource_name}" />'

    create_comp_name = f"CREATE_{resource_name.upper()}_FOR_{parent_name.upper()}"
    edit_comp_name = f"EDIT_{resource_name.upper()}_FOR_{parent_name.upper()}"
    validate_prop = f" validate={{validate_{resource_name}_related_fields}}" if _has_validations(ctx, concept) else ""

    create_comp = f"""
const {create_comp_name} = ({{ canEditParent = true }}) => {{
  const {{ id }} = useRecordContext();
  const [open, setOpen] = React.useState(false);
  const notify = useNotify();
  const refresh = useRefresh();
  const {{ permissions }} = usePermissions();
  const canWrite = (permissions?.['{resource_name}']?.includes('write') || permissions?.['*']?.includes('write')) && canEditParent;

  if (!canWrite) return null;

  const handleClick = () => setOpen(true);
  const handleClose = () => setOpen(false);

  const onSuccess = () => {{
    notify('{resource_name} created', {{ type: 'info', messageArgs: {{ smart_count: 1 }} }});
    setOpen(false);
    refresh();
  }};

  return (
    <>
      <Button onClick={{handleClick}} variant="contained" size="small">Add {resource_name}</Button>
      <Dialog open={{open}} onClose={{handleClose}} fullWidth maxWidth="md">
        <DialogTitle>Create {resource_name}</DialogTitle>
        <DialogContent>
          <Create resource="{resource_name}" redirect={{false}} mutationOptions={{{{ onSuccess }}}} title=" ">
            <SimpleForm defaultValues={{{{ {fk_field_name}: id }}}}{validate_prop}>
              <Grid container rowSpacing={{0}} columnSpacing={{2}}>
{create_fields}
              </Grid>
            </SimpleForm>
          </Create>
        </DialogContent>
      </Dialog>
    </>
  );
}} ;
"""
    components.append(create_comp)

    form_content = ""
    if my_children:
        form_content = f"""<TabbedForm record={{record}} onSubmit={{onSubmit}} syncWithLocation={{false}} toolbar={{<EditToolbar />}}{validate_prop}>
              <FormTab label="Summary">
                {workflow_ui}
                <Grid container rowSpacing={{0}} columnSpacing={{2}}>
{edit_fields}
                </Grid>
              </FormTab>
{child_tabs}
            </TabbedForm>"""
    else:
        form_content = f"""<SimpleForm record={{record}} onSubmit={{onSubmit}} toolbar={{<EditToolbar />}}{validate_prop}>
              {workflow_ui}
              <Grid container rowSpacing={{0}} columnSpacing={{2}}>
{edit_fields}
              </Grid>
            </SimpleForm>"""

    edit_comp = f"""
const {edit_comp_name} = ({{ canEditParent = true }}) => {{
  const record = useRecordContext();
  const [open, setOpen] = React.useState(false);
  const notify = useNotify();
  const refresh = useRefresh();
  const [update] = useUpdate();
  const {{ permissions }} = usePermissions();
  const canWrite = (permissions?.['{resource_name}']?.includes('write') || permissions?.['*']?.includes('write')) && canEditParent;

  const handleClick = (e) => {{
    e.stopPropagation();
    setOpen(true);
  }};

  const handleClose = () => setOpen(false);

  const onSubmit = (data) => {{
    update(
      '{resource_name}',
      {{ id: record.id, data: data, previousData: record }},
      {{
        onSuccess: () => {{
          notify('{resource_name} updated', {{ type: 'info', messageArgs: {{ smart_count: 1 }} }});
          setOpen(false);
          refresh();
        }},
        onError: (error) => {{
          notify('Error: ' + error.message, {{ type: 'warning' }});
        }},
        mutationMode: 'pessimistic'
      }}
    );
  }};

  const EditToolbar = props => (
    <Toolbar {{...props}}>
      <SaveButton disabled={{!canWrite}} />
      {{canWrite && <DeleteButton mutationMode="pessimistic" redirect={{false}} mutationOptions={{{{ onSuccess: () => {{ setOpen(false); refresh(); }} }}}} />}}
    </Toolbar>
  );

  if (!record) return null;

  return (
    <>
      <Button onClick={{handleClick}} size="small" color="primary">{{canWrite ? 'Edit' : 'Show'}}</Button>
      <Dialog open={{open}} onClose={{handleClose}} fullWidth maxWidth="md" onClick={{(e) => e.stopPropagation()}}>
        <DialogTitle><Title name="{resource_name}"{title_desc_prop} /></DialogTitle>
        <DialogContent>
            {form_content}
        </DialogContent>
      </Dialog>
    </>
  );
}};
"""
    components.append(edit_comp)

    return components


def _generate_prefill_component(concept: Dict[str, Any], group: Dict[str, Any]) -> str:
    group_name = group["name"]
    comp_name = f"PREFILL_{group_name.upper()}_FOR_{concept['name'].upper()}"
    source_concept_name = group["source_concept"]
    parent_fk = group["parent_fk_in_form"]
    source_part_of_field = group["source_part_of_field"]
    field_names = group["field_names"]
    pres_field = group.get("pres_field")
    prefix = group_name

    # setValue calls when loading from a saved record
    set_value_lines = []
    for fn in field_names:
        sf_name = fn[len(prefix) + 1:]
        set_value_lines.append(f"      setValue('{fn}', rec.{sf_name});")
    set_value_calls = "\n".join(set_value_lines)

    # Data object for the save operation
    save_data_lines = [f"        {source_part_of_field}: parentId,"]
    if pres_field:
        save_data_lines.append(f"        {pres_field}: saveName,")
    for fn in field_names:
        sf_name = fn[len(prefix) + 1:]
        if sf_name == pres_field:
            continue
        save_data_lines.append(f"        {sf_name}: watch('{fn}'),")
    save_data_str = "\n".join(save_data_lines)

    # After saving, update the presentation field in the form if it was expanded
    after_save_set = ""
    if pres_field and f"{prefix}_{pres_field}" in field_names:
        after_save_set = f"\n    setValue('{prefix}_{pres_field}', saveName);"

    group_label = group_name.replace("_", " ")

    return f"""
const {comp_name} = () => {{
  const {{ watch, setValue }} = useFormContext();
  const dataProvider = useDataProvider();
  const queryClient = useQueryClient();
  const [selected, setSelected] = React.useState('');
  const [saveOpen, setSaveOpen] = React.useState(false);
  const [saveName, setSaveName] = React.useState('');

  const parentId = watch('{parent_fk}');

  // Auto-set the parent FK when not yet selected (e.g. for users who own only one record)
  React.useEffect(() => {{
    if (parentId) return;
    dataProvider.getList('{parent_fk}', {{
      filter: {{}},
      pagination: {{ page: 1, perPage: 1 }},
      sort: {{ field: 'id', order: 'ASC' }}
    }}).then(({{ data }}) => {{
      if (data.length === 1) setValue('{parent_fk}', data[0].id);
    }}).catch(() => {{}});
  }}, [parentId, dataProvider, setValue]);

  const {{ data: records = [] }} = useGetList('{source_concept_name}', {{
    filter: {{ '{source_part_of_field}': parentId }},
    pagination: {{ page: 1, perPage: 100 }},
    sort: {{ field: 'id_presentation', order: 'ASC' }},
  }}, {{ enabled: !!parentId }});

  const handleSelect = (e) => {{
    const id = Number(e.target.value);
    setSelected(id);
    const rec = records.find(r => r.id === id);
    if (rec) {{
{set_value_calls}
    }}
  }};

  const handleSave = async () => {{
    if (!parentId || !saveName) return;
    const {{ data: created }} = await dataProvider.create('{source_concept_name}', {{
      data: {{
{save_data_str}
      }}
    }});{after_save_set}
    setSaveOpen(false);
    setSaveName('');
    await queryClient.invalidateQueries({{ queryKey: ['{source_concept_name}'] }});
    setSelected(created.id);
  }};

  return (
    <>
      <Box display="flex" alignItems="center" gap={{1}} mb={{1}} flexWrap="wrap">
        <MuiSelect value={{selected}} onChange={{handleSelect}} displayEmpty size="small" sx={{{{ minWidth: 220 }}}}>
          <MuiMenuItem value="">Load from saved {group_label}...</MuiMenuItem>
          {{records.map(r => <MuiMenuItem key={{r.id}} value={{r.id}}>{{r.id_presentation}}</MuiMenuItem>)}}
        </MuiSelect>
        <Button size="small" variant="outlined" onClick={{() => setSaveOpen(true)}}>Save as new</Button>
      </Box>
      <Dialog open={{saveOpen}} onClose={{() => setSaveOpen(false)}} fullWidth maxWidth="xs">
        <DialogTitle>Save {group_label}</DialogTitle>
        <DialogContent>
          <MuiTextField label="Name" value={{saveName}} onChange={{e => setSaveName(e.target.value)}} fullWidth autoFocus margin="dense" />
        </DialogContent>
        <DialogActions>
          <Button onClick={{() => setSaveOpen(false)}}>Cancel</Button>
          <Button onClick={{handleSave}} variant="contained" disabled={{!saveName}}>Save</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}};"""


def _generate_related_validation_component(ctx: Context, concept: Dict[str, Any]) -> str:
    validations = _validations_for_concept(ctx, concept)
    if not validations:
        return ""
    validation_json = json.dumps(validations)
    required_fields = [
        field["name"]
        for field in concept["fields"]
        if field["_be_not_null"] and field["_fe_visibility"] == "editable"
    ]
    required_fields_json = json.dumps(required_fields)
    suffix = concept["name"].upper()
    comp_name = f"RELATED_VALIDATION_INPUT_{concept['name'].upper()}"
    validate_name = f"validate_{concept['name']}_related_fields"
    return f"""
const RELATED_VALIDATIONS_{concept['name'].upper()} = {validation_json};
const REQUIRED_FIELDS_{concept['name'].upper()} = {required_fields_json};
const FREE_ENTRY_OPTION_{suffix} = '(type any value)';

const compatibleRows_{suffix} = (validation, values, ignoredColumn = null) => {{
  let rows = validation.rows;
  for (const [index, column] of validation.columns.entries()) {{
    if (column === ignoredColumn) continue;
    const value = values[column];
    if (value === undefined || value === null || value === '') continue;
    if (rows.some(row => row[index] === value)) {{
      rows = rows.filter(row => row[index] === value);
    }} else {{
      rows = rows.filter(row => row[index] === '*');
    }}
  }}
  return rows;
}};

const matchesValidationRow_{suffix} = (validation, values) =>
  compatibleRows_{suffix}(validation, values).some(row =>
    validation.columns.every((column, index) => row[index] === '*' || values[column] === row[index])
  );

const optionInfo_{suffix} = (validation, values, source) => {{
  const sourceIndex = validation.columns.indexOf(source);
  const rows = compatibleRows_{suffix}(validation, values, source);
  const concrete = Array.from(new Set(rows.map(row => row[sourceIndex]).filter(value => value !== '*'))).sort();
  const options = rows.some(row => row[sourceIndex] === '*') ? [...concrete, FREE_ENTRY_OPTION_{suffix}] : concrete;
  return {{ options }};
}};

const firstValidationForSource_{suffix} = (source) =>
  RELATED_VALIDATIONS_{concept['name'].upper()}.find(validation => validation.columns.includes(source));

const validationErrorText_{suffix} = (error) => {{
  if (!error) return '';
  if (typeof error === 'string') return error;
  if (typeof error.message === 'string') return error.message;
  if (error.message) return validationErrorText_{suffix}(error.message);
  return '';
}};

const {validate_name} = (values) => {{
  const errors = {{}};
  for (const field of REQUIRED_FIELDS_{concept['name'].upper()}) {{
    if (values[field] === undefined || values[field] === null || values[field] === '') {{
      errors[field] = 'Required';
    }}
  }}
  for (const validation of RELATED_VALIDATIONS_{concept['name'].upper()}) {{
    const complete = validation.columns.every(column => values[column] !== undefined && values[column] !== null && values[column] !== '');
    if (!complete) continue;
    if (!matchesValidationRow_{suffix}(validation, values)) {{
      for (const column of validation.columns) errors[column] = 'Invalid combination';
    }}
  }}
  return errors;
}};

const {comp_name} = ({{ source }}) => {{
  const {{ watch, setValue, formState }} = useFormContext();
  const values = watch();
  const validation = firstValidationForSource_{suffix}(source);
  const currentValue = values[source] ?? '';
  const {{ options }} = validation ? optionInfo_{suffix}(validation, values, source) : {{ options: [FREE_ENTRY_OPTION_{suffix}] }};
  const fieldError = formState.errors?.[source];

  const setFieldValue = (value) => {{
    const nextValue = value === FREE_ENTRY_OPTION_{suffix} ? '' : value;
    setValue(source, nextValue, {{ shouldDirty: true, shouldValidate: true }});
  }};

  const clearValidationGroup = () => {{
    if (!validation) return;
    for (const column of validation.columns) {{
      setValue(column, '', {{ shouldDirty: true, shouldValidate: true }});
    }}
  }};

  React.useEffect(() => {{
    if (!validation) return;
    for (const column of validation.columns) {{
      if (values[column]) continue;
      const {{ options: columnOptions }} = optionInfo_{suffix}(validation, values, column);
      const concrete = columnOptions.filter(option => option !== FREE_ENTRY_OPTION_{suffix});
      if (columnOptions.length === 1 && concrete.length === 1) {{
        setValue(column, concrete[0], {{ shouldDirty: true, shouldValidate: true }});
      }}
    }}
  }}, [validation, values, setValue]);

  return (
    <MuiValidationAutocomplete
      freeSolo
      options={{options}}
      value={{currentValue}}
      onChange={{(_event, value, reason) => {{
        if (reason === 'clear') {{
          clearValidationGroup();
          return;
        }}
        setFieldValue(value ?? '');
      }}}}
      onInputChange={{(_event, value, reason) => {{
        if (reason === 'clear') {{
          clearValidationGroup();
          return;
        }}
        if (reason === 'reset') return;
        setFieldValue(value ?? '');
      }}}}
      renderInput={{params => (
        <MuiValidationTextField
          {{...params}}
          label={{source.replaceAll('_', ' ')}}
          margin="none"
          size="small"
          error={{!!fieldError}}
          helperText={{validationErrorText_{suffix}(fieldError)}}
        />
      )}}
    />
  );
}};
"""


def _collect_validation_concepts(ctx: Context, concept: Dict[str, Any]) -> List[Dict[str, Any]]:
    result = []
    seen = set()

    def add(candidate: Dict[str, Any]):
        name = candidate["name"]
        if name in seen:
            return
        seen.add(name)
        if _has_validations(ctx, candidate):
            result.append(candidate)

    add(concept)
    for child in collect_all_descendants(concept["name"], ctx.concepts):
        add(child["concept"])
    return result


def generate(ctx: Context, concept: Dict[str, Any]) -> str:
    resource_name = concept["name"]
    title_desc_prop = f' description="{concept["description"].replace(chr(34), "&quot;")}"' if concept["description"] else ''

    owned_children = find_owned_children(resource_name, ctx.concepts)
    many_to_many_links = find_many_to_many_links(resource_name, ctx.concepts, ctx.concept_map)
    has_documents = concept["documents"]["enabled"]
    concept_workflow = ctx.business_schema.get("_concept_workflow", {}).get(resource_name)
    validation_concepts = _collect_validation_concepts(ctx, concept)

    field_components = generate_field_components(
        concept,
        ctx.concepts,
        ctx.concept_map,
        ctx.presentation_config,
        ctx.security_config,
        owned_children=owned_children,
        many_to_many_links=many_to_many_links,
        parent_workflow=concept_workflow,
    )

    react_admin_imports = get_optimized_react_admin_imports(
        concept, ctx.concepts, owned_children, many_to_many_links
    )

    has_prefill = bool(concept.get("_prefill_groups"))

    mui_imports = ["Grid"]
    if owned_children or many_to_many_links:
        mui_imports.extend(["Box", "Button", "Dialog", "DialogTitle", "DialogContent", "DialogActions"])
    elif concept_workflow:
        mui_imports.append("Box")
    if has_prefill:
        for item in ["Box", "Button", "Dialog", "DialogTitle", "DialogContent", "DialogActions"]:
            if item not in mui_imports:
                mui_imports.append(item)
        mui_imports.extend(["Select as MuiSelect", "MenuItem as MuiMenuItem", "TextField as MuiTextField"])
    if validation_concepts:
        mui_imports.extend([
            "Autocomplete as MuiValidationAutocomplete",
            "TextField as MuiValidationTextField",
        ])
    mui_imports_str = ", ".join(mui_imports)

    child_dialog_components_list = []
    visited_dialogs = set()
    if owned_children:
        for child_info in owned_children:
            child_dialog_components_list.extend(
                _generate_recursive_dialogs(ctx, child_info["concept"], resource_name, visited=visited_dialogs)
            )

    child_dialog_components = "\n".join(child_dialog_components_list)

    prefill_components = ""
    if has_prefill:
        prefill_parts = [_generate_prefill_component(concept, g) for g in concept["_prefill_groups"]]
        prefill_components = "\n".join(prefill_parts)
    validation_components = "\n".join(
        _generate_related_validation_component(ctx, validation_concept)
        for validation_concept in validation_concepts
    )

    doc_tab = ""
    if has_documents:
        doc_tab = _generate_document_tab(resource_name, concept["documents"], has_workflow=concept_workflow is not None)

    workflow_import = ""
    create_workflow_ui = ""
    if concept_workflow:
        wf_json_early = json.dumps(concept_workflow)
        workflow_import = "import { WorkflowSelector, useWorkflowCanEdit } from '../../components/workflow_selector';"
        create_workflow_ui = f'<WorkflowSelector workflow={{{wf_json_early}}} resource="{resource_name}" canEdit={{false}} />'

    component_imports = [
        f"import {{ Title }} from '../../components/title';",
        f"import {{ CustomEditToolbar }} from '../../components/custom_edit_toolbar';"
    ]
    if workflow_import:
        component_imports.append(workflow_import)

    if has_prefill or validation_concepts:
        component_imports.append("import { useFormContext } from 'react-hook-form';")
    if has_prefill:
        component_imports.append("import { useQueryClient } from '@tanstack/react-query';")
    if has_documents:
        component_imports.append(f"import {{ DocumentTab }} from '../../components/document_tab';")
    if "ReorderableDatagrid" in field_components["child_tabs"] or "ReorderableDatagrid" in child_dialog_components:
        component_imports.append(f"import {{ ReorderableDatagrid }} from '../../components/reorderable_datagrid';")
    if "RecursiveParentSelector" in field_components["create_fields"] or "RecursiveParentSelector" in field_components["edit_fields"]:
        component_imports.append(f"import {{ RecursiveParentSelector }} from '../../components/recursive_parent_selector';")
    if "FIELD_HELP_ICON" in field_components["create_fields"] or "FIELD_HELP_ICON" in field_components["edit_fields"] or "FIELD_HELP_ICON" in child_dialog_components:
        component_imports.append(f"import {{ FIELD_HELP_ICON }} from '../../components/field_help_icon';")
    component_imports_str = "\n".join(component_imports)

    id_field_show = ""
    id_field_edit = ""

    relations_tab = ""
    if field_components.get("m2m_edit_fields"):
        relations_tab = f"""
      <FormTab label="Relations">
        <Grid container rowSpacing={{0}} columnSpacing={{2}}>
{field_components["m2m_edit_fields"]}
        </Grid>
      </FormTab>"""

    edit_inner_component = ""
    validate_prop = f" validate={{validate_{resource_name}_related_fields}}" if _has_validations(ctx, concept) else ""
    if concept_workflow:
        wf_json = json.dumps(concept_workflow)
        inner_comp_name = f"{resource_name.upper()}_EDIT_FORM"
        if owned_children or many_to_many_links or has_documents:
            form_content = f"""<TabbedForm toolbar={{<CustomEditToolbar resource="{resource_name}" workflowCanEdit={{canEdit}} />}}{validate_prop}>
      <FormTab label="Summary">
        <WorkflowSelector workflow={{{wf_json}}} resource="{resource_name}" canEdit={{canEdit}} />
        <Box sx={{{{ pointerEvents: canEdit ? 'auto' : 'none', opacity: canEdit ? 1 : 0.6 }}}}>
          <Grid container rowSpacing={{0}} columnSpacing={{2}}>{id_field_edit}
            {field_components["edit_fields"]}
          </Grid>
        </Box>
      </FormTab>
      {field_components["child_tabs"]}
      {doc_tab}
      {relations_tab}
    </TabbedForm>"""
        else:
            form_content = f"""<SimpleForm toolbar={{<CustomEditToolbar resource="{resource_name}" workflowCanEdit={{canEdit}} />}}{validate_prop}>
      <WorkflowSelector workflow={{{wf_json}}} resource="{resource_name}" canEdit={{canEdit}} />
      <Box sx={{{{ pointerEvents: canEdit ? 'auto' : 'none', opacity: canEdit ? 1 : 0.6 }}}}>
        <Grid container rowSpacing={{0}} columnSpacing={{2}}>{id_field_edit}
          {field_components["edit_fields"]}
        </Grid>
      </Box>
    </SimpleForm>"""
        edit_inner_component = f"""
const {inner_comp_name} = () => {{
    const record = useRecordContext();
    const {{ permissions }} = usePermissions();
    const {{ data: identity, isLoading: identityLoading }} = useGetIdentity();
    const canEdit = useWorkflowCanEdit({wf_json}, record, identity, identityLoading);
    return (
        {form_content}
    );
}};"""
        edit_component = f"""<Edit title={{<Title name="{resource_name}"{title_desc_prop} />}} {{...props}}>
    <{inner_comp_name} />
  </Edit>"""
    elif owned_children or many_to_many_links or has_documents:
        edit_component = f"""<Edit title={{<Title name="{resource_name}"{title_desc_prop} />}} {{...props}}>
    <TabbedForm toolbar={{<CustomEditToolbar resource="{resource_name}" />}}{validate_prop}>
      <FormTab label="Summary">
        <Grid container rowSpacing={{0}} columnSpacing={{2}}>{id_field_edit}
          {field_components["edit_fields"]}
        </Grid>
      </FormTab>
      {field_components["child_tabs"]}
      {doc_tab}
      {relations_tab}
    </TabbedForm>
  </Edit>"""
    else:
        edit_component = f"""<Edit title={{<Title name="{resource_name}"{title_desc_prop} />}} {{...props}}>
    <SimpleForm toolbar={{<CustomEditToolbar resource="{resource_name}" />}}{validate_prop}>
      <Grid container rowSpacing={{0}} columnSpacing={{2}}>{id_field_edit}
        {field_components["edit_fields"]}
      </Grid>
    </SimpleForm>
  </Edit>"""

    return f"""import * as React from 'react';
import {{ {react_admin_imports} }} from 'react-admin';
import {{ {mui_imports_str} }} from '@mui/material';
{component_imports_str}
{field_components["imports"]}

{child_dialog_components}
{prefill_components}
{validation_components}
{edit_inner_component}

const {resource_name}_filters = [
{field_components["filter_fields"]}
];

export const {resource_name.upper()}_LIST = (props) => {{
  const {{ permissions }} = usePermissions();
  return (
    <List {{...props}} filters={{{resource_name}_filters}}>
      <Datagrid rowClick="edit">
        {field_components["list_fields"]}
      </Datagrid>
    </List>
  );
}};

export const {resource_name.upper()}_CREATE = (props) => {{
  const {{ permissions }} = usePermissions();
  return (
    <Create {{...props}}>
      <SimpleForm{validate_prop}>
        {create_workflow_ui}
        <Grid container rowSpacing={{0}} columnSpacing={{2}}>
          {field_components["create_fields"]}
        </Grid>
      </SimpleForm>
    </Create>
  );
}};

export const {resource_name.upper()}_EDIT = (props) => {{
  const {{ permissions }} = usePermissions();
  return (
    {edit_component}
  );
}};

export const {resource_name.upper()}_SHOW = (props) => (
  <Show title={{<Title name="{resource_name}"{title_desc_prop} />}} {{...props}}>
    <SimpleShowLayout>
      {id_field_show}
      {field_components["show_fields"]}
    </SimpleShowLayout>
  </Show>
);
"""
