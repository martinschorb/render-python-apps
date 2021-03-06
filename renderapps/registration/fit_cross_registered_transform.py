import renderapi
import numpy as np
from functools import partial
import logging
from renderapi.transform import AffineModel, RigidModel
from ..module.render_module import RenderModule, RenderParameters
from argschema.fields import Str, Int, Boolean
import marshmallow as mm
example_json = {
    "render": {
        "host": "ibs-forrestc-ux1",
        "port": 8080,
        "owner": "Forrest",
        "project": "M247514_Rorb_1",
        "client_scripts": "/pipeline/render/render-ws-java-client/src/main/scripts"
    },
    "ref_stack_shared_space": "LENS_REG_MARCH_21_DAPI_1_deconvnew",
    "ref_stack_dest_space": "ROUGHALIGN_MARCH_21_DAPI_1_CONS",
    "input_stack_src_space": "LENS_REG_MARCH_21_DAPI_1_deconvnew",
    "input_stack_shared_space": "LENS_REG_MARCH_21_DAPI_1_deconvnew",
    "output_stack": "ROUGHALIGN_LENS_DAPI_1_deconvnew",
    "one_transform_per_section": True,
    "transform_type": "rigid",
    "pool_size": 20,
    "stackResolutionX": 1,
    "stackResolutionY": 1,
    "stackResolutionZ": 1
}



class FitCrossRegisteredTransformParametersBase(RenderParameters):
    ref_stack_shared_space = Str(required=True,
                                 description= 'stack with ref tiles\
                                           in the space shared by input_stack_shared_space')
    ref_stack_dest_space = Str(required=True,
                               description= 'stack with ref tiles in the desired destination space')
    transform_type = Str(required = False, default = 'affine',
                         validate = mm.validate.OneOf(["affine","rigid"]),
                         description = "type of transformation to fit")
    one_transform_per_section = Boolean(required = False, default = False,
                                        desription = "whether to fit one transform per section or one per tile")
    pool_size = Int(required=False, default=20,
                    description= 'degree of parallelism (default 20)')
    stackResolutionX = Int(required=False, 
                           description= 'X stack resolution (nm) to save in \
                                     output stack (default use source stack)')
    stackResolutionY = Int(required=False, 
                           description= 'Y stack resolution (nm) to save in \
                                     output stack (default use source stack)')
    stackResolutionZ = Int(required=False, 
                           description= 'Z stack resolution (nm) to save in \
                                     output stack (default use source stack)')


class FitCrossRegisteredTransformParameters(FitCrossRegisteredTransformParametersBase):
    input_stack_src_space = Str(required=True,
                                description='stack with input tiles in an arbitrary source space')
    input_stack_shared_space = Str(required=False,
                                   description="stack with input tiles in the space shared by \
                                   ref_stack_shared_space (defaults to input_stack_src_space)")
    output_stack = Str(required=True,
                       description= 'name to call output version of \
                       input_stack_src_space with a transform added to bring it \
                       into the destination space')


logger = logging.getLogger(__name__)


def define_local_grid(ts, num_points):
    xvals = np.linspace(0, ts.width - 1, num=num_points, endpoint=True)
    yvals = np.linspace(0, ts.height - 1, num=num_points, endpoint=True)
    (xx, yy) = np.meshgrid(xvals, yvals)
    # unravel the grid and make it a Nx2 matrix of x,y columns
    xy = np.vstack([xx.ravel(), yy.ravel()]).T
    return xy


def process_z(r,
             ref_stack_shared_space,
             ref_stack_dest_space,
             input_stack_src_space,
             input_stack_shared_space,
             outstack,
             z,
             num_points=4,
             Transform = renderapi.transform.AffineModel,
             one_transform_per_section = False):

    ts_source = r.run(renderapi.tilespec.get_tile_specs_from_z, input_stack_src_space, z)

    final_list = []

    start_index = 0

    index_dict = {}
    # loop over the source tilespecs to figure out where they each go
    for ts in ts_source:

        # define a grid of local coordinates across the source tile
        xy_local_source = define_local_grid(ts, num_points)

        # map those local coordinates to the registered world coordinates
        xy_local_source_json = renderapi.coordinate.package_point_match_data_into_json(
            xy_local_source, ts.tileId, 'local')

        # package them into a list of lists for batch processing
        for elem in xy_local_source_json:
            final_list.append([elem])
        end_index = start_index + len(xy_local_source_json)
        # keep track of where in the final_list these coordinates are to pull out later
        index_dict[ts.tileId] = {
            'start_index': start_index, 'end_index': end_index}

        start_index = end_index
        # final_list.append(temp_list)

    print "xy_world_reg"
    # map all those local coordinates into world coordinates of the registered source stack
    xy_world_reg = r.run(renderapi.coordinate.local_to_world_coordinates_clientside,
                         input_stack_shared_space, final_list, z, number_of_threads=3)
    if input_stack_src_space != input_stack_shared_space:
        xy_world_source = r.run(renderapi.coordinate.local_to_world_coordinates_clientside,
                                input_stack_src_space, final_list, z, number_of_threads=3)
    else:
        xy_world_source = xy_world_reg

    print "xy_local_prealigned_json"
    # map those world coordinates to the local coordinates of the prealigned stack
    xy_local_prealigned_json = r.run(
        renderapi.coordinate.world_to_local_coordinates_clientside, ref_stack_shared_space, xy_world_reg, z, number_of_threads=3)

    print "xy_world_postaligned_json"
    # map those local coordinates to the world coordinates of the postaligned stack
    xy_world_postaligned_json = r.run(renderapi.coordinate.local_to_world_coordinates_clientside,
                                      ref_stack_dest_space, xy_local_prealigned_json, z, number_of_threads=3)

    if one_transform_per_section:
        all_source_world = np.zeros((0,2))
        all_aligned_world = np.zeros((0,2))

    # replace the transform for this tile with that transformation
    for ts in ts_source:
        xy_local_source = define_local_grid(ts, num_points)
        start = index_dict[ts.tileId]['start_index']
        end = index_dict[ts.tileId]['end_index']
        # pull out the correct elements of the list

        source_world_coords_json = xy_world_reg[start:end]
        aligned_world_coords_json = xy_world_postaligned_json[start:end]
        # packaged them into an numpy array

        good_aligned_world_coords = [
            c for c in aligned_world_coords_json if 'error' not in c.keys()]
        aligned_world_coords = renderapi.coordinate.unpackage_local_to_world_point_match_from_json(
            good_aligned_world_coords)
        notError = np.array([('error' not in d.keys())
                             for d in aligned_world_coords_json])

        good_source_world_coords = [
            c for c in source_world_coords_json if 'error' not in c.keys()]
        source_world_coords = renderapi.coordinate.unpackage_local_to_world_point_match_from_json(
            good_source_world_coords)
        source_world_coords = source_world_coords[notError, :]

        assert(source_world_coords.shape == aligned_world_coords.shape)
        if one_transform_per_section:
            all_source_world = np.vstack([all_source_world,source_world_coords])
            all_aligned_world = np.vstack([all_aligned_world,aligned_world_coords])
        else:
            # fit a tranformation
            tform = Transform()
            tform.estimate(source_world_coords, aligned_world_coords)
            ts.tforms = ts.tforms + [tform]

        logger.debug('from,to')
        for frompt, topt in zip(source_world_coords_json, aligned_world_coords_json):
            logger.debug((frompt, topt))
        # break

    if one_transform_per_section:
        tform = Transform()
        tform.estimate(source_world_coords, aligned_world_coords)
        for ts in ts_source:
            ts.tforms = ts.tforms + [tform]

    r.run(renderapi.client.import_tilespecs, outstack, ts_source)
    return None


class FitCrossRegisteredTransform(RenderModule):
    def __init__(self, schema_type=None, *args, **kwargs):
        if schema_type is None:
            schema_type = FitCrossRegisteredTransformParameters
        super(FitCrossRegisteredTransform, self).__init__(
            schema_type=schema_type, *args, **kwargs)

    def run(self):

        ref_stack_shared_space = self.args['ref_stack_shared_space']
        ref_stack_dest_space = self.args['ref_stack_dest_space']
        input_stack_src_space = self.args['input_stack_src_space']
        input_stack_shared_space = self.args.get(
            'input_stack_shared_space', input_stack_src_space)

        stackMetadata = renderapi.stack.get_stack_metadata(
            input_stack_src_space, render=self.render)
        stackResolutionX = self.args.get(
            'stackResolutionX', stackMetadata.stackResolutionX)
        stackResolutionY = self.args.get(
            'stackResolutionY', stackMetadata.stackResolutionY)
        stackResolutionZ = self.args.get(
            'stackResolutionZ', stackMetadata.stackResolutionZ)

        if self.args['transform_type'] == 'rigid':
            Transform=RigidModel
        else:
            logger.debug('CHOOSING AFFINE MODEL')
            Transform=AffineModel

        outstack = self.args['output_stack']
        myp = partial(process_z,
                      self.render,
                      ref_stack_shared_space,
                      ref_stack_dest_space,
                      input_stack_src_space,
                      input_stack_shared_space,
                      outstack,
                      Transform=Transform,
                      one_transform_per_section = self.args['one_transform_per_section'])

        zvalues = self.render.run(
            renderapi.stack.get_z_values_for_stack, input_stack_src_space)

        self.render.run(renderapi.stack.delete_stack, outstack)
        self.render.run(renderapi.stack.create_stack, outstack,
                        stackResolutionX=stackResolutionX,
                        stackResolutionY=stackResolutionY,
                        stackResolutionZ=stackResolutionZ)

        #for z in zvalues:
        #     myp(z)
        #     break
        with renderapi.client.WithPool(self.args['pool_size']) as pool:
           res = pool.map(myp, zvalues)
        self.render.run(renderapi.stack.set_stack_state,
                        outstack, state='COMPLETE')
        # break


if __name__ == "__main__":
    mod = FitCrossRegisteredTransform(input_data=example_json)
    mod.run()
