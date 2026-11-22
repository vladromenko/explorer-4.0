import hashlib
import json

import cv2
import numpy as np
import pytest

from explorer4 import so101_geometry as geometry


def test_known_marker_geometry_and_missing_detection_are_distinct(tmp_path, monkeypatch):
    calibration = json.loads(geometry.CALIBRATION.read_text())
    marker_from_object = np.eye(4)
    marker_from_object[2, 3] = -.016
    settings = {'marker_id': 7, 'marker_side_m': .02, 'marker_from_object': marker_from_object.tolist()}
    world_marker = np.eye(4)
    world_marker[:3, 3] = [.22, .02, .032]
    camera_marker = np.asarray(calibration['camera_from_robot']) @ world_marker
    square = np.array([[-.01, .01, 0], [.01, .01, 0], [.01, -.01, 0], [-.01, -.01, 0]])
    corners, _ = cv2.projectPoints(square, cv2.Rodrigues(camera_marker[:3, :3])[0], camera_marker[:3, 3],
                                   np.asarray(calibration['camera_matrix']), np.asarray(calibration['distortion']))
    marker = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), 7, 600)
    warp = cv2.getPerspectiveTransform(np.float32([[0, 0], [599, 0], [599, 599], [0, 599]]), corners.reshape(4, 2).astype(np.float32))
    grey = cv2.warpPerspective(marker, warp, (1280, 720), borderValue=255)
    result = geometry.marker_object_pose(np.repeat(grey[:, :, None], 3, axis=2), calibration, settings)
    assert result['valid'] and not result['uncertainty_calibrated']
    np.testing.assert_allclose(np.asarray(result['world_object_pose'])[:3, 3], [.22, .02, .016], atol=.015)
    missing = geometry.marker_object_pose(np.full((720, 1280, 3), 255, np.uint8), calibration, settings)
    assert missing == {'valid': False, 'reason': 'object_marker_missing_or_duplicated'}

    from explorer4 import knowledge, so101_station, station_check
    from explorer4.so101_vendor import measure
    frame = tmp_path / 'camera.png'
    assert cv2.imwrite(str(frame), grey)
    control = {'ok': True, 'image': str(frame), 'image_sha256': hashlib.sha256(frame.read_bytes()).hexdigest(),
               'calibration_sha256': hashlib.sha256(geometry.CALIBRATION.read_bytes()).hexdigest()}
    settings.update(instance_id='block-1', object_class='cube', size_m=[.032]*3)
    monkeypatch.setattr(geometry, 'configuration', lambda: settings)
    monkeypatch.setattr(station_check, 'capture', lambda: control)
    monkeypatch.setattr(knowledge, 'STORE', tmp_path / 'knowledge.json')
    monkeypatch.setattr(measure, 'measure', lambda *a, **kw: pytest.fail("No new segmentation is needed for a registered size"))
    station = so101_station.SO101Station()
    monkeypatch.setattr(station, 'available', lambda: True)
    measured = station.practice('cube', object_instance='block-1')
    assert measured['ok'] and measured['knowledge']['object_instance'] == 'block-1'
    assert measured['knowledge']['evidence']['dimension_source'] == 'operator_entered_on_registration'
    assert knowledge.best('cube', object_instance='block-1')['params']['width_m'] == .032
    assert not station.practice('cube', object_instance='unseen-block')['ok']
    assert knowledge.best('cube', object_instance='unseen-block') is None
    control['image_sha256'] = '0'*64
    assert not station.practice('cube', object_instance='block-1')['ok']


def test_fixed_tip_uses_measured_angles_offsets_and_distinct_jaw_frame():
    calibration = json.loads(geometry.CALIBRATION.read_text())
    a = geometry.fixed_frames([0, -30, 40, 10, 0, 0], calibration)
    b = geometry.fixed_frames([0, -30, 40, 10, 0, 50], calibration)
    np.testing.assert_allclose(a['gripper_frame_link'], b['gripper_frame_link'])
    assert not np.allclose(a['moving_jaw_so101_v1_link'], b['moving_jaw_so101_v1_link'])
    c = geometry.fixed_frames([0, -30, 40, 10, 0, 0], {**calibration, 'robot_offsets_deg': [0]*5})
    assert np.linalg.norm(c['gripper_frame_link'][:3, 3] - a['gripper_frame_link'][:3, 3]) > .005
    with pytest.raises(ValueError, match='measured native'):
        geometry.fixed_frames([float('nan')]*6, calibration)


def test_raw_recorder_keeps_causality_images_and_unknown_calibration(tmp_path, monkeypatch):
    from explorer4 import hardware, resources
    monkeypatch.setattr(resources, 'DATA', tmp_path)
    class Camera:
        info = {'device': 'fixture', 'camera_geometry_valid': False}
        frame = {'timestamp_ns': 1_000_000_000, 'sequence': 1, 'image': np.zeros((720, 1280, 3), np.uint8)}
        def __init__(self, *a):
            self.closed = False
        def start(self):
            pass
        def latest_before(self, cutoff):
            return self.frame
        def close(self):
            self.closed = True
    monkeypatch.setattr(hardware, 'CameraCapture', Camera)
    recorder = geometry.DonorGeometryRecorder(tmp_path / 'episode', {'enabled': True})
    recorder.start()
    sample = {'observation_timestamp_ns': 1_050_000_000, 'observation.state': [0]*6}
    recorder.add(sample)
    sample['observation_timestamp_ns'] = 1_200_000_000
    with pytest.raises(ValueError, match='fresh synchronized'):
        recorder.add(sample)
    meta = recorder.close()
    row = json.loads((recorder.directory / 'measurements.jsonl').read_text())
    assert row['jaw_opening_m'] is None and not row['metric_jaw_calibrated']
    assert not row['visual']['valid'] and not meta['physical_verified']
    assert row['image_sha256'] == hashlib.sha256((recorder.directory / row['image']).read_bytes()).hexdigest()
    assert meta['frames'] == 1


def test_configuration_is_only_preparation(tmp_path, monkeypatch):
    monkeypatch.setattr(geometry, 'CONFIG', tmp_path / 'capture.json')
    cfg = geometry.configure_capture(enabled=True, instance_id='cube-1', marker_side_m=.02, size_m=[.032]*3)
    assert cfg['enabled'] and not cfg['physical_verified']
    assert geometry.configuration() == cfg
    with pytest.raises(ValueError, match='метка|Метка'):
        geometry.configure_capture(enabled=True, instance_id='cube-1', marker_side_m=.05, size_m=[.032]*3)


def test_stale_optional_geometry_stops_existing_session_before_finalize(tmp_path, monkeypatch):
    from explorer4 import catalog, resources, session as sessions
    from explorer4.control import Control
    monkeypatch.setattr(resources, 'DATA', tmp_path)
    monkeypatch.setattr(catalog, 'DATA', tmp_path)
    catalog.initialize()
    monkeypatch.setattr(geometry, 'configuration', lambda: {'enabled': True})
    events = []
    class Source:
        def start(self, **kw):
            events.append('source_start')
            return {}
        def begin_episode(self):
            events.append('begin')
        def sample(self, *a, **kw):
            events.append('sample')
            return {'teleoperation_phase': 'following'}
        def close(self):
            events.append('source_closed')
            return []
    class Writer:
        id = 'fixture'
        root = tmp_path
        def __init__(self, *a, **kw):
            pass
        def add(self, sample):
            raise AssertionError('Stale geometry cannot become a usable record')
        def finish(self, outcome, provenance):
            events.append(outcome)
            assert provenance['donor_geometry']['physical_verified'] is False
    class Geometry:
        def __init__(self, *a):
            pass
        def start(self):
            events.append('geometry_start')
            return {'physical_verified': False}
        def add(self, sample):
            raise ValueError('stale geometry')
        def close(self):
            events.append('geometry_closed')
            return {'physical_verified': False}
    monkeypatch.setattr(sessions, 'HardwareSource', lambda **kw: Source())
    monkeypatch.setattr(sessions, 'EpisodeWriter', Writer)
    monkeypatch.setattr(geometry, 'DonorGeometryRecorder', Geometry)
    control = Control()
    control.stop_event.clear()
    control.expires = float('inf')
    session = sessions.Session(control)
    session.record_requested = True
    session._run('so101_pick_place', 'fixture', 'fixture')
    assert events == ['source_start', 'geometry_start', 'begin', 'sample', 'source_closed', 'geometry_closed', 'aborted']
    assert control.stop_event.is_set() and 'stale geometry' in session.error


def test_station_mask_selection_distinguishes_separate_objects_and_same_object_proposals():
    from explorer4.so101_vendor.instances import select_silhouette
    a = np.zeros((40, 60), bool)
    a[5:24, 4:22] = True
    b = np.zeros_like(a)
    b[10:32, 38:54] = True
    nested = b.copy()
    nested[:12] = False
    masks = [a, b, nested]
    scores = [.98, .77, .70]
    corners = [[40, 14], [50, 14], [50, 26], [40, 26]]
    with pytest.raises(ValueError, match='несколько'):
        select_silhouette(masks, scores)
    assert select_silhouette(masks, scores, corners) == 1
    with pytest.raises(ValueError, match='Нет силуэта'):
        select_silhouette([a], [.98], corners)


def test_station_cannot_bind_the_tag_on_one_component_to_the_largest_cube():
    from explorer4.so101_vendor.instances import metric_component, select_silhouette
    a = np.zeros((60, 80), bool)
    a[10:40, 5:32] = True
    b = np.zeros_like(a)
    b[17:32, 50:65] = True
    union = a | b
    corners = [[51, 18], [62, 18], [62, 30], [51, 30]]
    with pytest.raises(ValueError, match='несколько'):
        select_silhouette([union], [.99], corners)
    # A narrow bridge makes the combined proposal connected, but the other
    # two proposals independently support separate objects.
    union[25, 32:50] = True
    with pytest.raises(ValueError, match='несколько'):
        select_silhouette([union, a, b], [.99, .91, .87])
    assert select_silhouette([union, a, b], [.99, .91, .87], corners) == 2
    with pytest.raises(ValueError, match='Нет силуэта'):
        select_silhouette([union, a], [.99, .91], corners)
    speck = a.copy()
    speck[18:21, 51:54] = True
    edges = [[51, 18], [53, 18], [53, 20], [51, 20]]
    assert np.array_equal(metric_component(speck), a)
    with pytest.raises(ValueError, match='Нет силуэта'):
        select_silhouette([speck], [.99], edges)


def test_registered_dimensions_require_the_observed_instance(monkeypatch):
    settings = {'instance_id': 'tagged-block', 'object_class': 'cube', 'marker_id': 1, 'size_m': [.029]*3}
    monkeypatch.setattr(geometry, 'marker_object_pose',
                        lambda rgb, calibration, binding: {'valid': False, 'reason': 'object_marker_missing_or_duplicated'})
    assert not geometry.registered_dimensions(None, {}, settings, 'cube', 'tagged-block')['ok']
    assert not geometry.registered_dimensions(None, {}, settings, 'cube', 'other-block')['ok']
    monkeypatch.setattr(geometry, 'marker_object_pose',
                        lambda *args: {'valid': True, 'marker_corners_px': [[0,0],[1,0],[1,1],[0,1]], 'reprojection_rmse_px': .3})
    result = geometry.registered_dimensions(None, {}, settings, 'cube', 'tagged-block')
    assert result['model'] == 'registered_dimensions' and result['height_m'] == .029
    assert result['dimension_source'] == 'operator_entered_on_registration'


def test_cube_hypothesis_keeps_unobserved_height_explicit(tmp_path, monkeypatch):
    from explorer4 import perception
    from explorer4.so101_vendor import cuboid_vision, measure
    masks = np.zeros((1, 40, 40), np.uint8)
    masks[:, 6:28, 8:30] = 1
    capture = tmp_path / 'masks.npz'
    np.savez(capture, masks=masks)
    monkeypatch.setattr(perception, 'analyze', lambda *a, **kw: {
        'scores': [.9], 'masks': str(capture), 'input_sha256': 'fixture', 'overlay': 'fixture'})
    monkeypatch.setattr(cuboid_vision, 'fit_upright_cuboid', lambda *a, **kw: {
        'width_m': .03, 'length_m': .03, 'height_m': .03, 'height_sigma_m': .02,
        'center_m': [0, 0], 'yaw_rad': 0., 'silhouette_rmse_px': .1})
    monkeypatch.setattr(cuboid_vision, 'fit_upright_cube', lambda *a: (None, {
        'size_m': .03, 'silhouette_rmse_px': .12}))
    result = measure.measure('cube', image='fixture.jpg', settings={}, output_root=tmp_path)
    assert result['ok'] and result['width_m'] == .03
    assert not result['height_measured'] and result['model'] == 'cube, height assumed'
