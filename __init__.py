# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8-80 compliant>

bl_info = {
    "name": "Laubwerk lbw.gz format importer",
    "author": "Fabian Quosdorf",
    "version": (0, 1, 0),
    "blender": (2, 7, 2),
    "location": "File > Import",
    "description": "Import LBW.GZ, Import Laubwerk mesh, UV's, materials and textures",
    "warning": "",
    "wiki_url": "",
    "category": "Import"
}

import threading, time
import bpy, laubwerk, os.path
from bpy.props import (BoolProperty,
                       FloatProperty,
                       IntProperty,
                       StringProperty,
                       EnumProperty,
                       RemoveProperty
                       )
from bpy_extras.io_utils import (ImportHelper,
                                 path_reference_mode
                                 )


from io_import_laubwerk import import_lbw

# A global variable for the plant.
plant = None
current_path = ""
models = []
m_items = []
s_items = []
plant = None
locale = "en"
alt_locale = "en_US"
mt_loaded = False # Indicates if all model types have been loaded.
ms_loaded = False # Indicates if all model seasons have been loaded.
#TODO get the locale from the current blender installation via bpy.app.translations.locale. This can be void.


class ImportLBW(bpy.types.Operator, ImportHelper):
    """Load a Laubwerk LBW.GZ File"""
    bl_idname = "import_object.lbw"
    bl_label = "Import Laubwerk plant"
    #bl_options = {'PRESET', 'UNDO'}
        
    filename_ext = ".lbw.gz"
    short_ext = ".lbw"
    oldpath = ""
    watch_thread = None
    is_running = False
    restart_thread = False
    
    filter_glob = StringProperty(
            default="*.lbw;*.lbw.gz",
            options={'HIDDEN'},
            )
            
    filepath = StringProperty(name="File Path", 
        maxlen=1024, default="")  
#    directory = StringProperty(name="Directory", subtype='DIR_PATH', default="D:\\Program Files\\Laubwerk\\Plants", options={'HIDDEN', 'SKIP_SAVE'})    
    leaf_density = FloatProperty(name="Leaf density",
        description="The density of the leafs of the plant.",
        default=100.0, min=0.01, max=100.0, subtype='PERCENTAGE')
    model_id = 0
    render_mode = EnumProperty(items=[("PROXY","Convex Hull",""),("FULL","Full Geometry","")], name="Render")
    viewport_mode = EnumProperty(items=[("PROXY","Convex Hull",""),("FULL","Full Geometry","")], name="Viewport")
    lod_cull_thick = BoolProperty(name="Cull by Thickness", default=False)
    lod_min_thick = FloatProperty(name="Min. Thickness", default=0.1, min=0.1, max=10000.0, step=1.0)
    lod_cull_level = BoolProperty(name="Cull by Level", default=False)
    lod_max_level = IntProperty(name="Maximum Level", default=3, min=0, max=10, step=1)
    lod_subdiv = IntProperty(name="Subdivision", default=1, min=0, max=5, step=1)
    leaf_amount = FloatProperty(name="Leaf amount",
        description="The amount of leafs of the plant.",
        default=100.0, min=0.01, max=100.0, subtype='PERCENTAGE')
    
    def update_seasons(self, context):    
        global locale, alt_locale, s_items, plant
        print ("updating seasons")
        s_items = []
        for qualifier in plant.models[self["model_type"]].qualifiers:
            qualab = plant.models[self["model_type"]].qualifierLabels[qualifier] 
            qlabel = qualab[min(qualab)][0]
            if locale in qualab:
                qlabel = qualab[locale][0]
            elif alt_locale in qualab:
                qlabel = qualab[alt_locale][0]
            s_items.append((qualifier,qlabel,""))
        self["model_season"] = plant.defaultModel.defaultQualifier
    
    def model_type_callback(self, context):
        global m_items, mt_loaded
        """ Queries the plant object for available models and creates a dropdown list """
        return m_items
        
    def model_season_callback(self, context):
        global s_items, ms_loaded
        return s_items
#        if ms_loaded:
#            return s_items
#        else:
#            return [("Loading...","Loading...","")]
        
    model_type = EnumProperty(items=model_type_callback, name="Model", update=update_seasons)
    model_season = EnumProperty(items=model_season_callback, name="Season")
    
    def execute(self, context):
        global plant
        # Stop the thread
        self.is_running = False
        # Set the model_id to the currently selected model type.
        self.model_id = models.index(self.model_type)
        # Use this dictionary to store additional parameters like season and so on.
        keywords = self.as_keywords(ignore=("filter_glob","oldpath","is_running","restart_thread","watch_thread"
											))
        keywords["model_id"] =  self.model_id
        keywords["plant"] = plant
        return import_lbw.LBWImportDialog.load(self, context, **keywords)   
        
    def invoke(self, context, event):
        global mt_loaded, ms_loaded
        print ('invoked')
        self.oldpath = self.filepath
        self.restart_thread = False
        self.is_running = True
        mt_loaded = False
        ms_loaded = False
        self.watch_thread = lbw_watch(self)                
        self.watch_thread.start()
        context.window_manager.fileselect_add(self)
        # This would be the right spot to change the directory.
        return {'RUNNING_MODAL'} 
        
    def reinit_values(self):
        """
        Called when a new file is selected. Resets the values of the import parameters to default.
        """
        global mt_loaded, ms_loaded
        ms_loaded = False
        mt_loaded = False
        self.restart_thread = True        
        self.leaf_density=100.0
        self.render_mode="FULL"
        self.viewport_mode="PROXY"
        self.lod_cull_thick = False
        self.lod_min_thick = 0.1
        self.lod_cull_level = False
        self.lod_max_level = 1
        self.leaf_amount=100.0
        self.lod_subdiv = 1

    
    def draw(self, context):
        global locale, alt_locale, plant
        layout = self.layout
        if not self.filepath == self.oldpath:
            self.oldpath = self.filepath
            plant = None
            if os.path.isfile(self.filepath):
                self.reinit_values()
            
        if plant:
            pname = plant.labels[min(plant.labels)][0]
            if locale in plant.labels:
                pname = plant.labels[locale][0]
            elif alt_locale in plant.labels:
                pname = plant.labels[alt_locale][0]
            # Create the UI entries.
            layout.label("%s(%s)" % (pname, plant.name))
            if mt_loaded is False:
                layout.label("Loading...")
            sub = layout.column()
            sub.active = mt_loaded == True
            sub.prop(self,"model_type")
            sub.prop(self,"model_season")
            row = layout.row()
            box = row.box()
            box.label("Display settings")
            box.prop(self,"render_mode")
            box.prop(self,"viewport_mode")
            row = layout.row()
            box2 = row.box()
            box2.label("Level of Detail")
            box2.prop(self,"leaf_density")
            box = box2.box()
            box.prop(self,"lod_cull_thick")
            subrow = box.row()
            subrow.active = self.lod_cull_thick == True
            subrow.prop(self,"lod_min_thick")
            box = box2.box()
            box.prop(self,"lod_cull_level")
            subrow = box.row()
            subrow.active = self.lod_cull_level == True
            subrow.prop(self,"lod_max_level")
            box2.prop(self,"lod_subdiv")
            box2.prop(self,"leaf_amount")
        else:
            layout.label("Choose a Laubwerk file.")

            
class lbw_watch(threading.Thread):
    
    def __init__(self, clob):
        threading.Thread.__init__(self)
        self.daemon = True # so Blender can quit cleanly
        self.name='lbw_watch'
        self.clob = clob # The calling class instance.
    
    def run(self):
        global models, plant, m_items, s_items, locale, mt_loaded
        while self.clob.is_running:
            time.sleep(0.1) # sleep 100 Milliseconds.
            try:
                if self.clob.restart_thread:
                    # Recreate the m_types and m_items
                    m_items = []
                    s_items = []
                    mt_loaded = False
                    plant = laubwerk.load(self.clob.filepath)
                    if plant:
                        self.clob.restart_thread = False
                        for model in plant.models:
                            time.sleep(0.05)
                            if self.clob.restart_thread:
                                break
                            label = model.labels[min(model.labels)]
                            if locale in model.labels:
                                label = model.labels[locale]
                            m_items.append((str(model.name),str(label),""))
                            models.append(str(model.name))
                        self.clob.model_type = plant.defaultModel.name
                        self.clob.model_id = models.index(self.clob.model_type)
                        mt_loaded = True
            except Exception as detail:
                print("lbw watch exception:", detail)

                
class lbwPanel(bpy.types.Panel):     # panel to display laubwerk plant specific properties.
    bl_space_type = "PROPERTIES"       # show up in: properties view
    bl_region_type = "WINDOW"           # show up in: object context
    bl_label = "Laubwerk Plant"           # name of the new panel
    bl_context = "object"    
    tr = None 
        
    @classmethod
    def poll(self, context):
        global plant, current_path
        if context.object and "lbw_path" in context.object:
            if not context.object["lbw_path"] == current_path:            
                current_path = context.object["lbw_path"]
                plant = laubwerk.load(current_path)
                self.object = context.object
            return True
            
    
    def draw(self, context):
        # display value of Laubwerk plant, of the active object
        global plant, locale, alt_locale, current_path
        layout = self.layout
        
        if plant:
            pname = plant.labels[min(plant.labels)][0]
            if locale in plant.labels:
                pname = plant.labels[locale][0]
            elif alt_locale in plant.labels:
                pname = plant.labels[alt_locale][0]
            layout.label("%s(%s)" % (pname, plant.name))
            row = layout.row()
            box = row.box()
            box.label("Display settings")
            box.prop(context.object,"render_mode")
            box.prop(context.object,"viewport_mode")
            row = layout.row()
            box2 = row.box()
            box2.label("Level of Detail")
            box2.prop(context.object,"leaf_density")
            box = box2.box()
            box.prop(context.object,"lod_cull_thick")
            subrow = box.row()
            subrow.active = context.object.lod_cull_thick == True
            subrow.prop(context.object,"lod_min_thick")
            box = box2.box()
            box.prop(context.object,"lod_cull_level")
            subrow = box.row()
            subrow.active = context.object.lod_cull_level == True
            subrow.prop(context.object,"lod_max_level")
            box2.prop(context.object,"lod_subdiv")
            box2.prop(context.object,"leaf_amount")                 
 
		
def menu_func_import(self, context):
    self.layout.operator(ImportLBW.bl_idname, text="Laubwerk plant (.lbw.gz)")


def register():
    bpy.utils.register_class(lbwPanel)   # register panel
    # create LBW Settings
    bpy.types.Object.leaf_density = FloatProperty(name="Leaf density",
        description="The density of the leafs of the plant.",
        default=100.0, min=0.01, max=100.0, subtype='PERCENTAGE')
    bpy.types.Object.render_mode = EnumProperty(items=[("PROXY","Convex Hull",""),("FULL","Full Geometry","")], name="Render", options={'HIDDEN'})
    bpy.types.Object.viewport_mode = EnumProperty(items=[("PROXY","Convex Hull",""),("FULL","Full Geometry","")], name="Viewport", options={'HIDDEN'})
    bpy.types.Object.lod_cull_thick = BoolProperty(name="Cull by Thickness", default=False)
    bpy.types.Object.lod_min_thick = FloatProperty(name="Min. Thickness", default=0.1, min=0.1, max=10000.0, step=1.0)
    bpy.types.Object.lod_cull_level = BoolProperty(name="Cull by Level", default=False)
    bpy.types.Object.lod_max_level = IntProperty(name="Maximum Level", default=3, min=0, max=10, step=1)
    bpy.types.Object.lod_subdiv = IntProperty(name="Subdivision", default=1, min=0, max=5, step=1)
    bpy.types.Object.leaf_amount = FloatProperty(name="Leaf amount",
        description="The amount of leafs of the plant.",
        default=100.0, min=0.01, max=100.0, subtype='PERCENTAGE', options={'HIDDEN'})
    
    bpy.utils.register_module(__name__)
	
    bpy.types.INFO_MT_file_import.append(menu_func_import)
    		


def unregister():
    bpy.utils.unregister_module(__name__)
    # Check if the Panel is actually registered and remove it.
    if "bl_rna" in lbwPanel.__dict__:
        bpy.utils.unregister_class(lbwPanel)

    bpy.types.INFO_MT_file_import.remove(menu_func_import)

if __name__ == "__main__":
    register()