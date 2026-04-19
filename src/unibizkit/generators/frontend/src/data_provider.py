import json
from ..context import Context
from .resources.helpers import find_many_to_many_links


def generate(ctx: Context) -> str:
    m2m_config = {}
    for concept in ctx.concepts:
        resource_name = concept["name"]
        links = find_many_to_many_links(resource_name, ctx.concepts, ctx.concept_map)
        if links:
            m2m_config[resource_name] = {}
            for link in links:
                field_name = link.get("field_name")
                m2m_config[resource_name][field_name] = {
                    'resource': link["join_table"],
                    'linkField': link["my_fk"],
                    'targetField': link["other_fk"]
                }

    m2m_config_json = json.dumps(m2m_config, indent=2)

    return f"""import {{ supabaseDataProvider }} from 'ra-supabase';
import {{ supabaseClient }} from './supabaseClient';

const supabaseUrl = process.env.REACT_APP_SUPABASE_URL;
const supabaseKey = process.env.REACT_APP_SUPABASE_KEY;

const baseDataProvider = supabaseDataProvider({{
  instanceUrl: supabaseUrl,
  apiKey: supabaseKey,
  supabaseClient: supabaseClient
}});

const m2mConfig = {m2m_config_json};

export const dataProvider = {{
  ...baseDataProvider,

  getOne: async (resource, params) => {{
    const result = await baseDataProvider.getOne(resource, params);
    const config = m2mConfig[resource];

    if (config) {{
      await Promise.all(Object.keys(config).map(async (field) => {{
         const {{ resource: joinResource, linkField, targetField }} = config[field];
         const {{ data }} = await supabaseClient
             .from(joinResource)
             .select(`"${{targetField}}"`)
             .eq(`"${{linkField}}"`, result.data.id);

         if (data) {{
             result.data[field] = data.map(item => item[targetField]);
         }}
      }}));
    }}
    return result;
  }},

  create: async (resource, params) => {{
     const config = m2mConfig[resource];
     let m2mIds = {{}};

     if (config) {{
        Object.keys(config).forEach(field => {{
           if (params.data[field]) {{
               m2mIds[field] = params.data[field];
               delete params.data[field];
           }}
        }});
     }}

     const result = await baseDataProvider.create(resource, params);

     if (config && Object.keys(m2mIds).length > 0) {{
        const id = result.data.id;
        await Promise.all(Object.keys(m2mIds).map(async (field) => {{
            const {{ resource: joinResource, linkField, targetField }} = config[field];
            const ids = m2mIds[field];
            if (ids && ids.length > 0) {{
                const rows = ids.map(targetId => ({{
                    [linkField]: id,
                    [targetField]: targetId
                }}));
                await supabaseClient.from(joinResource).insert(rows);
            }}
        }}));
        Object.assign(result.data, m2mIds);
     }}
     return result;
  }},

  update: async (resource, params) => {{
     const config = m2mConfig[resource];
     let m2mIds = {{}};

     if (config) {{
        Object.keys(config).forEach(field => {{
           if (params.data[field] !== undefined) {{
               m2mIds[field] = params.data[field];
               delete params.data[field];
           }}
        }});
     }}

     const result = await baseDataProvider.update(resource, params);

     if (config && Object.keys(m2mIds).length > 0) {{
        const id = result.data.id;
        await Promise.all(Object.keys(m2mIds).map(async (field) => {{
            const {{ resource: joinResource, linkField, targetField }} = config[field];
            const newIds = m2mIds[field];

                            // Delete existing links
                            await supabaseClient.from(joinResource).delete().eq(`"${{linkField}}"`, id);
                            // Insert new links
                            if (newIds && newIds.length > 0) {{                const rows = newIds.map(targetId => ({{
                    [linkField]: id,
                    [targetField]: targetId
                }}));
                await supabaseClient.from(joinResource).insert(rows);
            }}
        }}));
        Object.assign(result.data, m2mIds);
     }}
     return result;
  }}
}};
"""
