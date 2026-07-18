import json
from typing import Any, Dict, List

# Generated components that live in src/components/ and therefore must not be
# imported from the react-admin package.
CUSTOM_FIELD_COMPONENTS = {'RelatedValidationInput', 'MarkdownInput', 'MarkdownField', 'PrecisionDateTimeInput'}


def find_owned_children(parent_concept_name: str, concepts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    children = []
    for concept in concepts:
        for field in concept["fields"]:
            if field["type"] == "relation_to_one" and field["subtype"] == "part_of":
                if field["target"] == parent_concept_name:
                    children.append({
                        'concept': concept,
                        'field_name': field["name"],
                        'rel': field
                    })
    return children


def build_m2m_config(concepts: List[Dict[str, Any]], concept_map: Dict[str, Any]) -> Dict[str, Any]:
    m2m_config = {}
    for concept in concepts:
        resource_name = concept["name"]
        links = find_many_to_many_links(resource_name, concepts, concept_map)
        if links:
            m2m_config[resource_name] = {}
            for link in links:
                m2m_config[resource_name][link["field_name"]] = {
                    'resource': link["join_table"],
                    'linkField': link["my_fk"],
                    'targetField': link["other_fk"],
                    'target': link["target_concept"]["name"]
                }
    return m2m_config


def find_many_to_many_links(concept_name: str, concepts: List[Dict[str, Any]], concept_map: Dict[str, Any]) -> List[Dict[str, Any]]:
    links = []
    concept = concept_map.get(concept_name)
    if not concept:
        return links

    for field in concept["fields"]:
        if field["type"] == "relation_to_many":
            target_name = field["target"]
            target_concept = concept_map.get(target_name)
            if target_concept:
                is_one_to_many = any(
                    tf["type"] == "relation_to_one" and tf["target"] == concept_name
                    for tf in target_concept["fields"]
                )
                if not is_one_to_many:
                    table1, table2 = concept_name, target_name
                    join_table = f"{min(table1, table2)}_{max(table1, table2)}"
                    links.append({
                        'target_concept': target_concept,
                        'join_table': join_table,
                        'my_fk': f"{concept_name}_id",
                        'other_fk': f"{target_name}_id",
                        'field_name': field["name"],
                        'rel': field
                    })

    for other_concept in concepts:
        other_name = other_concept["name"]
        if other_name == concept_name:
            continue
        for field in other_concept["fields"]:
            if field["type"] == "relation_to_many" and field["target"] == concept_name:
                is_one_to_many = any(
                    mf["type"] == "relation_to_one" and mf["target"] == other_concept["name"]
                    for mf in concept["fields"]
                )
                if not is_one_to_many:
                    table1, table2 = other_name, concept_name
                    join_table = f"{min(table1, table2)}_{max(table1, table2)}"
                    links.append({
                        'target_concept': other_concept,
                        'join_table': join_table,
                        'my_fk': f"{concept_name}_id",
                        'other_fk': f"{other_name}_id",
                        'field_name': other_concept["plural_name"],
                        'rel': field
                    })

    return links


def collect_all_descendants(concept_name: str, concepts: List[Dict[str, Any]], visited=None) -> List[Dict[str, Any]]:
    if visited is None:
        visited = set()
    descendants = []
    children = find_owned_children(concept_name, concepts)
    for child in children:
        c_name = child["concept"]["name"]
        if c_name not in visited:
            visited.add(c_name)
            descendants.append(child)
            descendants.extend(collect_all_descendants(c_name, concepts, visited))
    return descendants


def filter_list_fields(pool: List[str], current: List[str], rule_str: str) -> List[str]:
    result = list(current)
    parts = [p.strip() for p in rule_str.split(',') if p.strip()]
    for part in parts:
        if part == '*':
            for name in pool:
                if name not in result:
                    result.append(name)
        elif part.startswith('!'):
            pattern = part[1:]
            if pattern.startswith('>='):
                target = pattern[2:]
                if target in pool:
                    idx = pool.index(target)
                    for name in pool[idx:]:
                        if name in result:
                            result.remove(name)
            elif pattern.startswith('>'):
                target = pattern[1:]
                if target in pool:
                    idx = pool.index(target)
                    for name in pool[idx+1:]:
                        if name in result:
                            result.remove(name)
            elif pattern.startswith('<='):
                target = pattern[2:]
                if target in pool:
                    idx = pool.index(target)
                    for name in pool[:idx+1]:
                        if name in result:
                            result.remove(name)
            elif pattern.startswith('<'):
                target = pattern[1:]
                if target in pool:
                    idx = pool.index(target)
                    for name in pool[:idx]:
                        if name in result:
                            result.remove(name)
            elif pattern.endswith('*'):
                prefix = pattern[:-1]
                result = [name for name in result if not name.startswith(prefix)]
            else:
                if pattern in result:
                    result.remove(pattern)
        elif part.startswith('>='):
            target = part[2:]
            if target in pool:
                idx = pool.index(target)
                for name in pool[idx:]:
                    if name not in result:
                        result.append(name)
        elif part.startswith('>'):
            target = part[1:]
            if target in pool:
                idx = pool.index(target)
                for name in pool[idx+1:]:
                    if name not in result:
                        result.append(name)
        elif part.startswith('<='):
            target = part[2:]
            if target in pool:
                idx = pool.index(target)
                for name in pool[:idx+1]:
                    if name not in result:
                        result.append(name)
        elif part.startswith('<'):
            target = part[1:]
            if target in pool:
                idx = pool.index(target)
                for name in pool[:idx]:
                    if name not in result:
                        result.append(name)
        elif '*' in part:
            prefix = part.split('*')[0]
            for name in pool:
                if name.startswith(prefix) and name not in result:
                    result.append(name)
        elif '[' in part and part.endswith(']'):
            name, target = part[:-1].split('[', 1)
            if name not in pool:
                continue
            if name in result:
                result.remove(name)
            if target == '0':
                result.insert(0, name)
            elif target == '-1':
                result.append(name)
            elif target in result:
                idx = result.index(target)
                result.insert(idx + 1, name)
            else:
                result.append(name)
        else:
            name = part
            if name in pool:
                if name in result:
                    result.remove(name)
                result.append(name)
    return result


def get_optimized_react_admin_imports(
    concept: Dict[str, Any],
    concepts: List[Dict[str, Any]],
    owned_children: List[Dict[str, Any]] = None,
    many_to_many_links: List[Dict[str, Any]] = None
) -> str:
    needed_components = {
        'List', 'Create', 'Edit', 'Show',
        'SimpleShowLayout', 'SimpleForm', 'Datagrid', 'DatagridConfigurable',
        'TextField', 'TextInput', 'required', 'useRecordContext', 'usePermissions',
        'useGetIdentity'
    }

    all_descendants = []
    if owned_children:
        all_descendants = collect_all_descendants(concept["name"], concepts)

    if all_descendants or many_to_many_links:
        needed_components.update([
            'TabbedForm', 'FormTab', 'ReferenceManyField', 'useRecordContext',
            'useNotify', 'useRefresh', 'useUpdate', 'EditButton', 'DeleteButton',
            'Toolbar', 'SaveButton'
        ])

    if concept["documents"]["enabled"]:
        needed_components.update(['TabbedForm', 'FormTab'])

    if concept.get("_prefill_groups"):
        needed_components.update(['useDataProvider', 'useGetList'])

    if all_descendants:
        for child in all_descendants:
            for field in child["concept"]["fields"]:
                if field["_fe_component"] not in CUSTOM_FIELD_COMPONENTS:
                    needed_components.add(field["_fe_component"])
                if field["_fe_list_component"] not in CUSTOM_FIELD_COMPONENTS:
                    needed_components.add(field["_fe_list_component"])

    if many_to_many_links:
        needed_components.update([
            'ReferenceInput', 'SelectInput', 'ReferenceField', 'DeleteButton',
            'ReferenceArrayInput', 'SelectArrayInput', 'ReferenceArrayField',
            'SingleFieldList', 'ChipField'
        ])

    for field in concept["fields"]:
        if field["_fe_component"] not in CUSTOM_FIELD_COMPONENTS:
            needed_components.add(field["_fe_component"])
        if field["_fe_list_component"] not in CUSTOM_FIELD_COMPONENTS:
            needed_components.add(field["_fe_list_component"])

        if field["type"] == "relation_to_one":
            needed_components.update(['ReferenceInput', 'ReferenceField', 'SelectInput'])
            if field["_fe_component"] == "AutocompleteInput":
                needed_components.add('AutocompleteInput')
        elif field["type"] == "relation_to_many":
            needed_components.add('EditButton')

    presentation_config = concept["id_presentation"]
    if presentation_config["show"]:
        needed_components.update(['TextField', 'TextInput'])
    if any("show" in action["placement"] for action in concept.get("actions", [])):
        needed_components.add("TopToolbar")
    if any("edit" in action["placement"] for action in concept.get("actions", [])):
        needed_components.update(["TopToolbar", "ShowButton"])

    return ', '.join(sorted(needed_components))


def generate_field_components(
    concept: Dict[str, Any],
    concepts: List[Dict[str, Any]],
    concept_map: Dict[str, Any],
    presentation_config: Dict[str, Any],
    security_config: Dict[str, Any],
    owned_children: List[Dict[str, Any]] = None,
    exclude_fields: List[str] = None,
    many_to_many_links: List[Dict[str, Any]] = None,
    parent_workflow: Dict[str, Any] = None,
    customization: bool = True,
) -> Dict[str, str]:
    imports = []
    list_fields = []
    # Create/edit forms are built as named entries: a field name, or a composite
    # block name (prefill group) whose lines accumulate under one entry. The
    # runtime reorders whole entries (renderFormEntries), so blocks move as units.
    create_entries: Dict[str, List[str]] = {}
    edit_entries: Dict[str, List[str]] = {}
    show_fields = []
    child_tabs = []
    filter_fields = []
    m2m_edit_fields = []

    def _entry(entries: Dict[str, List[str]], name: str) -> List[str]:
        return entries.setdefault(name, [])

    exclude_fields = exclude_fields or []

    create_grid_pos = 0
    edit_grid_pos = 0
    m2m_grid_pos = 0

    list_fields.append(("id_presentation", '<TextField source="id_presentation" label="Id" />'))
    show_fields.append(("id_presentation", '<TextField source="id_presentation" label="Id" />'))

    # Track which prefill group headers have been inserted
    added_prefill_headers = set()
    validation_fields = {
        field["name"]
        for field in concept["fields"]
        if field.get("_validation_csv_filename")
    }

    def update_grid(current_pos, width, fields_list):
        if width == 6:
            if current_pos % 12 == 3:
                fields_list.append('        <Grid item xs={12} sm={3} />')
                current_pos += 3
        if (current_pos % 12) + width > 12:
            current_pos = 0
        current_pos += width
        return current_pos

    filter_fields.append(("id_presentation", f'  <TextInput label="Search" source="id_presentation@ilike" alwaysOn />'))

    if owned_children:
        for child_info in owned_children:
            child_concept = child_info["concept"]
            fk_field_name = child_info["field_name"]
            child_name = child_concept["name"]
            child_plural = child_concept["plural_name"]
            parent_name = concept["name"]

            child_raw_columns = [("id_presentation", '<TextField source="id_presentation" label="Id" />')]

            relevant_fields = [f for f in child_concept["fields"] if f["name"] != fk_field_name and f["_fe_visibility"] != "internal"]
            for field in relevant_fields:
                fname = field["name"]
                comp = field["_fe_list_component"]
                comp_options = field["_fe_list_component_options"]
                fdesc = field["description"]
                if fdesc:
                    flabel = fname.replace('_', ' ').capitalize()
                    fdesc_escaped = fdesc.replace('"', '&quot;')
                    fcol_label = f' label={{<FIELD_HELP_ICON label="{flabel}" help="{fdesc_escaped}" />}}'
                else:
                    fcol_label = ''

                if field["type"] == "relation_to_one":
                    target = field["target"]
                    if field.get("on_delete") == "snapshot_data":
                        snapshot_source = f"_{fname}_deleted_snapshot"
                        child_raw_columns.append((fname, f'<DeletedSnapshotReference source="{fname}" reference="{target}" snapshotSource="{snapshot_source}"{fcol_label} />'))
                    else:
                        child_raw_columns.append((fname, f'<ReferenceField source="{fname}" reference="{target}" link={{false}}{fcol_label}><TextField source="id_presentation" /></ReferenceField>'))
                elif field["type"] == "decimal" and field.get("subtype") == "money":
                    currency = presentation_config["currency"]
                    number_locale = presentation_config["number_locale"]
                    child_raw_columns.append((fname, f'<NumberField source="{fname}" options={{{{ style: "currency", currency: "{currency}" }}}} locales="{number_locale}"{fcol_label} />'))
                else:
                    child_raw_columns.append((fname, f'<{comp} source="{fname}"{comp_options}{fcol_label} />'))

            child_all_names = [f[0] for f in child_raw_columns]
            child_result_names = presentation_config.get("_list_fields", {}).get(child_name, child_all_names)

            child_html_map = {name: html for name, html in child_raw_columns}
            child_columns = [child_html_map[name] for name in child_result_names if name in child_html_map]

            dialog_comp_name = f"CREATE_{child_name.upper()}_FOR_{parent_name.upper()}"
            edit_dialog_comp_name = f"EDIT_{child_name.upper()}_FOR_{parent_name.upper()}"

            can_edit_prop = " canEditParent={canEdit}" if parent_workflow else ""
            child_columns.append(f"<{edit_dialog_comp_name}{can_edit_prop} />")
            delete_guard = "canEdit && " if parent_workflow else ""
            child_columns.append(f"{{{delete_guard}(permissions?.['{child_name}']?.includes('write') || permissions?.['*']?.includes('write')) && <DeleteButton mutationMode='pessimistic' redirect={{false}} />}}")

            sort_prop = " sort={{ field: 'id_presentation', order: 'ASC' }}"
            datagrid_comp = "Datagrid"
            if any(f["name"] == "part_of_order" for f in child_concept["fields"]):
                sort_prop = " sort={{ field: 'part_of_order', order: 'ASC' }}"
                datagrid_comp = "ReorderableDatagrid"
                child_columns.append(f'<NumberField source="part_of_order" sx={{{{ display: "none" }}}} />')

            child_columns_str = '\n        '.join(child_columns)

            create_can_edit_prop = " canEditParent={canEdit}" if parent_workflow else ""
            tab_content = f"""
      <FormTab label="{child_plural}">
        <ReferenceManyField reference="{child_name}" target="&quot;{fk_field_name}&quot;" label={{false}}{sort_prop}>
          <Box display="flex" justifyContent="flex-end" mb={{1}}>
            <{dialog_comp_name}{create_can_edit_prop} />
          </Box>
          <{datagrid_comp}>
            {child_columns_str}
          </{datagrid_comp}>
        </ReferenceManyField>
      </FormTab>"""
            child_tabs.append(tab_content)

    for field in concept["fields"]:
        field_name = field["name"]

        # Insert prefill selector header before the first field of each group
        prefill_group_name = field.get("_prefill_group")
        if prefill_group_name and prefill_group_name not in added_prefill_headers:
            comp_name = f"PREFILL_{prefill_group_name.upper()}_FOR_{concept['name'].upper()}"
            header_item = f"        <Grid item xs={{12}}><{comp_name} /></Grid>"
            _entry(create_entries, prefill_group_name).append(header_item)
            _entry(edit_entries, prefill_group_name).append(header_item)
            create_grid_pos = 0
            edit_grid_pos = 0
            added_prefill_headers.add(prefill_group_name)

        comp_type = field["_fe_component"]
        component_options = field["_fe_component_options"]
        list_comp = field["_fe_list_component"]
        list_component_options = field["_fe_list_component_options"]
        width_units = field["_fe_grid_width"]
        visibility = field["_fe_visibility"]
        is_required = field["_be_not_null"] or field["required"] == "ask_after_login"

        if field_name in exclude_fields:
            continue

        if field.get("_prefill_is_pres_field"):
            continue

        grid_props = f"xs={{12}} sm={{{width_units}}}"

        validation = ' validate={[required()]}' if is_required and visibility != "read_only" else ''
        full_width = ' fullWidth'
        margin = ' margin="none" size="small"'

        disabled_prop = ""
        if visibility == "read_only":
            disabled_prop = " disabled"
        elif security_config["authentication_required"]:
            disabled_prop = f" disabled={{!permissions?.['{concept['name']}.{field_name}']?.includes('write')}}"

        description = field["description"]
        if description:
            label = field_name.replace('_', ' ').capitalize()
            desc_escaped = description.replace('"', '&quot;')
            label_prop = f' label={{<FIELD_HELP_ICON label="{label}" help="{desc_escaped}" />}} InputLabelProps={{{{ shrink: true }}}}'
            col_label_prop = f' label={{<FIELD_HELP_ICON label="{label}" help="{desc_escaped}" />}}'
        else:
            label_prop = ''
            col_label_prop = ''

        input_html = ""

        if field_name in validation_fields and field["type"] == "string":
            input_html = f'          <RELATED_VALIDATION_INPUT_{concept["name"].upper()} source="{field_name}" />'
            filter_fields.append((field_name, f'  <TextInput source="{field_name}" />'))

        elif field["type"] == "relation_to_one":
            target = field["target"]

            if concept["_type"] == "recursive_part_of" and field.get("subtype") == "part_of":
                presentation = concept["id_presentation"]
                separator = presentation["separator"]
                pres_fields = presentation["fields"]
                display_field = pres_fields[-1]

                rps_label = f'{{<FIELD_HELP_ICON label="{field_name.replace("_", " ").capitalize()}" help="{desc_escaped}" />}}' if description else f'"{field_name}"'
                input_html = f'          <RecursiveParentSelector source="{field_name}" reference="{target}" label={rps_label} separator="{separator}" displayField="{display_field}"{disabled_prop} />'
                width_units = 6
                grid_props = f"xs={{12}} sm={{{width_units}}}"

                filter_inner = f'<SelectInput optionText="id_presentation" />'
                filter_fields.append((field_name, f'  <ReferenceInput source="{field_name}" reference="{target}" sort={{{{ field: "id_presentation", order: "ASC" }}}}>{filter_inner}</ReferenceInput>'))
            else:
                input_inner = ""
                if comp_type == "AutocompleteInput":
                    input_inner = f'<AutocompleteInput optionText="id_presentation" filterToQuery={{searchText => ({{ "id_presentation@ilike": searchText }})}}{full_width}{validation}{margin}{disabled_prop}{label_prop} />'
                else:
                    input_inner = f'<SelectInput optionText="id_presentation"{full_width}{validation}{margin}{disabled_prop}{label_prop} />'

                if field.get("on_delete") == "snapshot_data":
                    snapshot_source = f"_{field_name}_deleted_snapshot"
                    input_html = f'          <DeletedSnapshotReferenceInput source="{field_name}" reference="{target}" snapshotSource="{snapshot_source}" sort={{{{ field: "id_presentation", order: "ASC" }}}}>{input_inner}</DeletedSnapshotReferenceInput>'
                else:
                    input_html = f'          <ReferenceInput source="{field_name}" reference="{target}" sort={{{{ field: "id_presentation", order: "ASC" }}}}>{input_inner}</ReferenceInput>'

                filter_inner = input_inner.replace(f'{validation}{margin}{disabled_prop}{label_prop}', '')
                filter_fields.append((field_name, f'  <ReferenceInput source="{field_name}" reference="{target}" sort={{{{ field: "id_presentation", order: "ASC" }}}}>{filter_inner}</ReferenceInput>'))

        elif field["type"] == "relation_to_many":
            target_name = field["target"]
            target_concept = concept_map.get(target_name)
            is_one_to_many = False
            if target_concept:
                for target_field in target_concept["fields"]:
                    if target_field["type"] == "relation_to_one" and target_field["target"] == concept["name"]:
                        is_one_to_many = True
                        break
            if is_one_to_many:
                pass
            else:
                continue

        elif field["type"] == "markdown":
            # Full-width editor; the MUI text-input props do not apply. No list
            # filter either: long-form content is not useful as a filter.
            input_html = f'          <MarkdownInput source="{field_name}"{validation}{disabled_prop}{col_label_prop} />'

        elif field["type"] == "json":
            json_layout = " multiline rows={4}" if field["size"] == "l" else ""
            # Editability follows field permissions (e.g. the designer reviewer
            # role edits _design.design); without auth (or without the
            # customization system) json stays read-only as before.
            json_disabled = disabled_prop if (customization and security_config["authentication_required"]) else " disabled"
            input_html = f'          <TextInput source="{field_name}" format={{value => value == null ? "" : JSON.stringify(value, null, 2)}} parse={{value => value ? JSON.parse(value) : null}}{json_layout} fullWidth margin="none" size="small"{json_disabled}{label_prop} />'

        elif field["type"] == "enum":
            enum_values = field["enum_values"]
            choices_str = ', '.join([f"{{ id: '{val}', name: '{val}' }}" for val in enum_values])
            choices_array = f"[{choices_str}]"
            input_html = f'          <SelectInput source="{field_name}" choices={{{choices_array}}}{full_width}{validation}{margin}{disabled_prop}{label_prop} />'
            filter_fields.append((field_name, f'  <SelectInput source="{field_name}" choices={{{choices_array}}} />'))

        else:
            extra_props = ""
            if field["size"] == "l":
                extra_props = " multiline rows={4}"
            if field["type"] == "decimal":
                pass

            input_html = f'          <{comp_type} source="{field_name}"{component_options}{extra_props}{full_width}{validation}{margin}{disabled_prop}{label_prop} />'
            if field["type"] == "datetime":
                filter_fields.append((field_name, f'  <{comp_type} source="{field_name}@gte"{component_options} label="{field_name.replace("_", " ").capitalize()} from" />'))
                filter_fields.append((field_name + "_to", f'  <{comp_type} source="{field_name}@lte"{component_options} label="{field_name.replace("_", " ").capitalize()} to" />'))
            else:
                filter_fields.append((field_name, f'  <{comp_type} source="{field_name}" />'))

        list_html = ""
        show_html = ""
        if field["type"] == "relation_to_one":
            target = field["target"]
            if field.get("on_delete") == "snapshot_data":
                snapshot_source = f"_{field_name}_deleted_snapshot"
                list_html = f'      <DeletedSnapshotReference source="{field_name}" reference="{target}" snapshotSource="{snapshot_source}"{col_label_prop} />'
                show_html = list_html
            else:
                list_html = f'      <ReferenceField source="{field_name}" reference="{target}" link={{false}}{col_label_prop}><TextField source="id_presentation" /></ReferenceField>'
                show_html = f'      <ReferenceField source="{field_name}" reference="{target}"{col_label_prop}><TextField source="id_presentation" /></ReferenceField>'
        elif field["type"] == "relation_to_many":
            pass
        elif field["type"] == "decimal":
            if field.get("subtype") == "money":
                currency = presentation_config["currency"]
                number_locale = presentation_config["number_locale"]
                list_html = f"""      <NumberField source="{field_name}" options={{{{ style: 'currency', currency: '{currency}' }}}} locales="{number_locale}"{col_label_prop} />"""
                show_html = list_html
            else:
                list_html = f'      <{list_comp} source="{field_name}"{col_label_prop} />'
                show_html = list_html
        elif field["type"] == "json":
            list_html = f'      <FunctionField label="{field_name}" render={{record => record?.{field_name} == null ? "" : JSON.stringify(record.{field_name})}} />'
            show_html = f'      <FunctionField label="{field_name}" render={{record => record?.{field_name} == null ? "" : JSON.stringify(record.{field_name}, null, 2)}} />'
        else:
            list_html = f'      <{list_comp} source="{field_name}"{list_component_options}{col_label_prop} />'
            show_html = list_html

        # The workflow-injected state field is internal (forms use the
        # WorkflowSelector instead) but is still a useful list column.
        if list_html and (visibility != "internal" or field_name == "state"):
            list_fields.append((field_name, list_html))
        if show_html and visibility != "internal":
            show_fields.append((field_name, show_html))

        if visibility != "internal":
            if input_html:
                # CGrid (components/customization.jsx) applies the runtime
                # presentation customizations: per-role field hiding, label and
                # width overrides from presentation-custom-NN.jsonc. `entry` is
                # the reorder unit the field belongs to (its prefill block).
                # With designer 'off' no customization system exists and the
                # field is a plain grid cell, as before the feature.
                entry_name = prefill_group_name or field_name
                if customization:
                    entry_prop = f' entry="{entry_name}"' if prefill_group_name else ''
                    cgrid_open = f'        <CGrid concept="{concept["name"]}" field="{field_name}"{entry_prop} {grid_props}>'
                    cgrid_close = "        </CGrid>"
                else:
                    cgrid_open = f'        <Grid item {grid_props}>'
                    cgrid_close = "        </Grid>"
                if visibility == "editable":
                    create_lines = _entry(create_entries, entry_name)
                    create_grid_pos = update_grid(create_grid_pos, width_units, create_lines)
                    create_lines.append(cgrid_open)
                    create_lines.append(input_html)
                    create_lines.append(cgrid_close)

                    if concept["_type"] == "recursive_part_of" and field.get("subtype") == "part_of":
                        remaining = 12 - (create_grid_pos % 12)
                        if remaining < 12 and remaining > 0:
                            create_lines.append(f'        <Grid item xs={{12}} sm={{{remaining}}} />')
                            create_grid_pos += remaining

                edit_lines = _entry(edit_entries, entry_name)
                edit_grid_pos = update_grid(edit_grid_pos, width_units, edit_lines)
                edit_lines.append(cgrid_open)
                edit_lines.append(input_html)
                edit_lines.append(cgrid_close)

                if concept["_type"] == "recursive_part_of" and field.get("subtype") == "part_of":
                    remaining = 12 - (edit_grid_pos % 12)
                    if remaining < 12 and remaining > 0:
                        edit_lines.append(f'        <Grid item xs={{12}} sm={{{remaining}}} />')
                        edit_grid_pos += remaining

        if field["type"] == "relation_to_many":
            target_name = field["target"]
            target_concept = concept_map.get(target_name)
            is_one_to_many = False
            target_fk = ""
            if target_concept:
                for target_field in target_concept["fields"]:
                    if target_field["type"] == "relation_to_one" and target_field["target"] == concept["name"]:
                        is_one_to_many = True
                        target_fk = target_field["name"]
                        break
            if is_one_to_many:
                ref_many = f"""        <Grid item xs={{12}} sm={{{width_units}}}>
          <ReferenceManyField reference="{target_name}" target="&quot;{target_fk}&quot;" label="{field["name"]}">
            <Datagrid>
              <TextField source="id_presentation" />
              <EditButton />
            </Datagrid>
          </ReferenceManyField>
        </Grid>"""
                edit_lines = _entry(edit_entries, field["name"])
                edit_grid_pos = update_grid(edit_grid_pos, width_units, edit_lines)
                edit_lines.append(ref_many)

    if many_to_many_links:
        for link_info in many_to_many_links:
            target_name = link_info["target_concept"]["name"]
            field_name = link_info.get("field_name", f"{target_name}s")
            rel = link_info.get("rel", {})

            rel_size = rel["size"]
            width_units = 3
            if rel_size in ['m', 'l']:
                width_units = 6

            m2m_grid_pos = update_grid(m2m_grid_pos, width_units, m2m_edit_fields)

            input_block = f"""        <Grid item xs={{12}} sm={{{width_units}}}>
          <ReferenceArrayInput source="{field_name}" reference="{target_name}" sort={{{{ field: "id_presentation", order: "ASC" }}}}>
            <SelectArrayInput optionText="id_presentation" fullWidth margin="none" size="small" />
          </ReferenceArrayInput>
        </Grid>"""
            m2m_edit_fields.append(input_block)

            show_block = f"""      <ReferenceArrayField source="{field_name}" reference="{target_name}">
        <SingleFieldList>
          <ChipField source="id_presentation" />
        </SingleFieldList>
      </ReferenceArrayField>"""
            show_fields.append((field_name, show_block))

    concept_name = concept["name"]
    all_names = [f[0] for f in list_fields]
    result_names = presentation_config.get("_list_fields", {}).get(concept_name, all_names)
    html_map = {name: html for name, html in list_fields}
    # Default (visible) columns from the evaluated list_field_rules DSL; the
    # remaining pool columns stay available through the column selector. The
    # runtime split into order/omit happens in customizationConfig.js so
    # presentation-custom overlays can change it per role.
    default_names = [name for name in result_names if name in html_map]
    extra_names = [name for name in all_names if name not in result_names]

    # Filters follow the full column set, so a user-added column can be filtered
    # too. The id_presentation search keeps alwaysOn only when it is a default
    # column; as an extra it stays available behind the Add-filter button.
    filter_html_map = {name: html for name, html in filter_fields}
    final_filter_fields = [filter_html_map[name] for name in result_names if name in filter_html_map] \
                        + [filter_html_map[name].replace(' alwaysOn', '') for name in extra_names if name in filter_html_map]

    # Old-style inline outputs, used by the designer-'off' emission (columns
    # and show fields baked into the resource, defaults first then the extras
    # hidden through DatagridConfigurable `omit`).
    inline_extra_names = [name for name in all_names if name not in default_names]
    inline_list_fields = [html_map[name] for name in default_names] \
                       + [html_map[name] for name in inline_extra_names]

    return {
        'imports': '\n'.join(imports),
        'list_column_entries': list_fields,
        'list_names': all_names,
        'list_default_names': default_names,
        'list_fields_inline': '\n'.join(inline_list_fields),
        'list_omit_json': json.dumps(inline_extra_names),
        'show_fields_inline': '\n'.join(html for _, html in show_fields),
        'create_fields': '\n'.join(line for lines in create_entries.values() for line in lines),
        'edit_fields': '\n'.join(line for lines in edit_entries.values() for line in lines),
        'create_form_entries': [(name, '\n'.join(lines)) for name, lines in create_entries.items()],
        'edit_form_entries': [(name, '\n'.join(lines)) for name, lines in edit_entries.items()],
        'm2m_edit_fields': '\n'.join(m2m_edit_fields),
        'show_field_entries': show_fields,
        'child_tabs': '\n'.join(child_tabs),
        'filter_fields': ',\n'.join(final_filter_fields),
    }
