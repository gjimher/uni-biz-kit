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


def _generate_document_tab(concept_name: str, docs: Dict[str, Any]) -> str:
    tags_js = ", ".join(f"'{t}'" for t in docs["tags"])
    versioned_js = "true" if docs["versioned"] else "false"
    return f"""
      <FormTab label="Documents">
        <DocumentTab conceptName="{concept_name}" tags={{[{tags_js}]}} versioned={{{versioned_js}}} />
      </FormTab>"""


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

    create_comp = f"""
const {create_comp_name} = () => {{
  const {{ id }} = useRecordContext();
  const [open, setOpen] = React.useState(false);
  const notify = useNotify();
  const refresh = useRefresh();
  const {{ permissions }} = usePermissions();
  const canWrite = permissions?.['{resource_name}']?.includes('write') || permissions?.['*']?.includes('write');

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
            <SimpleForm defaultValues={{{{ {fk_field_name}: id }}}}>
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
        form_content = f"""<TabbedForm record={{record}} onSubmit={{onSubmit}} syncWithLocation={{false}} toolbar={{<EditToolbar />}}>
              <FormTab label="Summary">
                {workflow_ui}
                <Grid container rowSpacing={{0}} columnSpacing={{2}}>
{edit_fields}
                </Grid>
              </FormTab>
{child_tabs}
            </TabbedForm>"""
    else:
        form_content = f"""<SimpleForm record={{record}} onSubmit={{onSubmit}} toolbar={{<EditToolbar />}}>
              {workflow_ui}
              <Grid container rowSpacing={{0}} columnSpacing={{2}}>
{edit_fields}
              </Grid>
            </SimpleForm>"""

    edit_comp = f"""
const {edit_comp_name} = () => {{
  const record = useRecordContext();
  const [open, setOpen] = React.useState(false);
  const notify = useNotify();
  const refresh = useRefresh();
  const [update] = useUpdate();
  const {{ permissions }} = usePermissions();
  const canWrite = permissions?.['{resource_name}']?.includes('write') || permissions?.['*']?.includes('write');

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
        <DialogTitle><Title name="{resource_name}" /></DialogTitle>
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


def generate(ctx: Context, concept: Dict[str, Any]) -> str:
    resource_name = concept["name"]

    owned_children = find_owned_children(resource_name, ctx.concepts)
    many_to_many_links = find_many_to_many_links(resource_name, ctx.concepts, ctx.concept_map)
    has_documents = concept["documents"]["enabled"]

    field_components = generate_field_components(
        concept,
        ctx.concepts,
        ctx.concept_map,
        ctx.presentation_config,
        ctx.security_config,
        owned_children=owned_children,
        many_to_many_links=many_to_many_links
    )

    react_admin_imports = get_optimized_react_admin_imports(
        concept, ctx.concepts, owned_children, many_to_many_links
    )

    concept_workflow = ctx.business_schema.get("_concept_workflow", {}).get(resource_name)

    mui_imports = ["Grid"]
    if owned_children or many_to_many_links:
        mui_imports.extend(["Box", "Button", "Dialog", "DialogTitle", "DialogContent", "DialogActions"])
    elif concept_workflow:
        mui_imports.append("Box")
    mui_imports_str = ", ".join(mui_imports)

    child_dialog_components_list = []
    visited_dialogs = set()
    if owned_children:
        for child_info in owned_children:
            child_dialog_components_list.extend(
                _generate_recursive_dialogs(ctx, child_info["concept"], resource_name, visited=visited_dialogs)
            )

    child_dialog_components = "\n".join(child_dialog_components_list)

    doc_tab = ""
    if has_documents:
        doc_tab = _generate_document_tab(resource_name, concept["documents"])

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

    if has_documents:
        component_imports.append(f"import {{ DocumentTab }} from '../../components/document_tab';")
    if "ReorderableDatagrid" in field_components["child_tabs"] or "ReorderableDatagrid" in child_dialog_components:
        component_imports.append(f"import {{ ReorderableDatagrid }} from '../../components/reorderable_datagrid';")
    if "RecursiveParentSelector" in field_components["create_fields"] or "RecursiveParentSelector" in field_components["edit_fields"]:
        component_imports.append(f"import {{ RecursiveParentSelector }} from '../../components/recursive_parent_selector';")
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
    if concept_workflow:
        wf_json = json.dumps(concept_workflow)
        inner_comp_name = f"{resource_name.upper()}_EDIT_FORM"
        if owned_children or many_to_many_links or has_documents:
            form_content = f"""<TabbedForm toolbar={{<CustomEditToolbar resource="{resource_name}" workflowCanEdit={{canEdit}} />}}>
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
            form_content = f"""<SimpleForm toolbar={{<CustomEditToolbar resource="{resource_name}" workflowCanEdit={{canEdit}} />}}>
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
        edit_component = f"""<Edit title={{<Title name="{resource_name}" />}} {{...props}}>
    <{inner_comp_name} />
  </Edit>"""
    elif owned_children or many_to_many_links or has_documents:
        edit_component = f"""<Edit title={{<Title name="{resource_name}" />}} {{...props}}>
    <TabbedForm toolbar={{<CustomEditToolbar resource="{resource_name}" />}}>
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
        edit_component = f"""<Edit title={{<Title name="{resource_name}" />}} {{...props}}>
    <SimpleForm toolbar={{<CustomEditToolbar resource="{resource_name}" />}}>
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
      <SimpleForm>
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
  <Show title={{<Title name="{resource_name}" />}} {{...props}}>
    <SimpleShowLayout>
      {id_field_show}
      {field_components["show_fields"]}
    </SimpleShowLayout>
  </Show>
);
"""
