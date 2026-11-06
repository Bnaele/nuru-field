const paths = {
  leaf: <><path d="M20.8 3.2C14.5 3.4 6.6 5.6 4.3 11.3c-1.4 3.5.2 7.3 3.7 8.5 3.8 1.3 7.7-.9 9.2-4.3 1.5-3.4 1.6-7.7 3.6-12.3Z" /><path d="M3.8 20.3c3-4.8 6.4-8 11.8-10.6" /></>,
  location: <><path d="M20 10.4c0 5.8-8 10.7-8 10.7s-8-4.9-8-10.7a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></>,
  camera: <><path d="M4 7.5h3l1.3-2h7.4l1.3 2h3A2 2 0 0 1 22 9.5v8A2 2 0 0 1 20 19.5H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2Z" /><circle cx="12" cy="13.5" r="3.5" /></>,
  chat: <><path d="M20 11.5a7.5 7.5 0 0 1-8 7.5 8.6 8.6 0 0 1-3.5-.7L3 20l1.7-4.2A7.4 7.4 0 0 1 4 12a7.5 7.5 0 0 1 8-7.5 7.5 7.5 0 0 1 8 7Z" /><path d="M8 12h.01M12 12h.01M16 12h.01" /></>,
  arrow: <><path d="M5 12h14" /><path d="m13 6 6 6-6 6" /></>,
  spark: <><path d="m12 2 1.6 6.4L20 10l-6.4 1.6L12 18l-1.6-6.4L4 10l6.4-1.6L12 2Z" /><path d="m19 16 .7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7L19 16Z" /></>,
  cloud: <><path d="M17.5 18.5H7a4.5 4.5 0 1 1 .9-8.9A5.7 5.7 0 0 1 19 11.5a3.5 3.5 0 0 1-1.5 7Z" /><path d="M8.5 21.2 7.6 22M12 21.2l-.8.8M15.5 21.2l-.8.8" /></>,
  water: <><path d="M12 2.5S5.4 10 5.4 14.3A6.6 6.6 0 0 0 18.6 14.3C18.6 10 12 2.5 12 2.5Z" /><path d="M8.8 14.5a3.2 3.2 0 0 0 3.2 3.1" /></>,
  wind: <><path d="M3 8h12.5a2.5 2.5 0 1 0-2.3-3.5" /><path d="M3 12h16.5a2.5 2.5 0 1 1-2.3 3.5" /><path d="M3 16h8" /></>,
  close: <><path d="m6 6 12 12M18 6 6 18" /></>,
  check: <path d="m5 12 4.2 4.2L19 6.5" />,
  upload: <><path d="M12 16V3" /><path d="m7 8 5-5 5 5" /><path d="M5 14v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5" /></>,
  pulse: <path d="M3 12h3l2-5 4 10 2.5-5H21" />,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m15.5 15.5 4.5 4.5" /></>,
};

export default function Icon({ name, size = 20, stroke = 1.8 }) {
  const common = {
    width: size, height: size, viewBox: '0 0 24 24', fill: 'none',
    stroke: 'currentColor', strokeWidth: stroke, strokeLinecap: 'round',
    strokeLinejoin: 'round', 'aria-hidden': true,
  };
  return <svg {...common}>{paths[name]}</svg>;
}