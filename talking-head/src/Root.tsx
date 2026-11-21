import {Composition, type CalculateMetadataFunction} from 'remotion';
import {Main} from './Main';
import {Mograph} from './mograph/Mograph';
import type {MographProps} from './mograph/types';
import {FPS, makeTime} from './time';
import type {Job} from './types';

type Props = {job: Job; portrait: boolean};

const EMPTY: Job = {title: 'empty', source: 'footage.mp4', srcEnd: 1, cuts: [], sections: []};

const EMPTY_MOGRAPH: MographProps = {
  kind: 'punch', portrait: false, fps: 30, frames: 90, text: 'Motion graphic', em: [], kicker: '', sub: '',
  palette: {bg: '#1d3557', bg_deep: '#00121f', text: '#ffffff', accent: '#29a8d6', accent_hi: '#9fe3fb', dim: '#3d6380'},
};

// A faceless video's motion graphic scene (scripts/mograph.py): size, fps and length come from the props
const mographMeta: CalculateMetadataFunction<MographProps> = ({props}) => ({
  durationInFrames: Math.max(1, props.frames),
  fps: props.fps,
  width: props.portrait ? 1080 : 1920,
  height: props.portrait ? 1920 : 1080,
});

const meta: CalculateMetadataFunction<Props> = ({props}) => ({durationInFrames: Math.max(1, makeTime(props.job).totalFrames)});

// Props come from th.py: --props=<job>/work/props.json, shape {job: {...}}
export const Root = () => (
  <>
    <Composition id="Landscape" component={Main} fps={FPS} width={1920} height={1080} durationInFrames={1} defaultProps={{job: EMPTY, portrait: false}} calculateMetadata={meta} />
    <Composition id="Portrait" component={Main} fps={FPS} width={1080} height={1920} durationInFrames={1} defaultProps={{job: EMPTY, portrait: true}} calculateMetadata={meta} />
    <Composition id="Mograph" component={Mograph} fps={30} width={1920} height={1080} durationInFrames={90} defaultProps={EMPTY_MOGRAPH} calculateMetadata={mographMeta} />
  </>
);
