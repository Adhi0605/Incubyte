export function CarArt({ category = 'Sedan', color = '#b3bcb5' }) {
  const tall = /suv|truck/i.test(category);
  return <svg viewBox="0 0 420 200" aria-hidden="true" className="car-art">
    <defs><linearGradient id={`body-${color.replace('#', '')}`} x2="0" y2="1"><stop stopColor={color}/><stop offset="1" stopColor="#596760"/></linearGradient></defs>
    <ellipse cx="213" cy="164" rx="169" ry="13" fill="#172c2318"/>
    <path d={tall ? 'M37 124 L68 107 L106 52 Q111 44 130 44 H271 Q285 46 304 88 L357 109 Q379 116 384 137 L378 153 H35Z' : 'M34 124 L82 109 L129 65 Q138 57 159 57 H253 Q271 59 309 104 L363 116 Q381 121 384 141 L375 154 H36Z'} fill={`url(#body-${color.replace('#', '')})`} stroke="#334a3e" strokeWidth="2"/>
    <path d={tall ? 'M115 54 H174 V94 H83Z M184 54 H264 L288 94 H184Z' : 'M137 67 H187 V104 H97Z M197 67 H249 L288 104 H197Z'} fill="#233c34"/>
    <path d="M45 122 H79 L69 134 H40 M345 122 L375 130 L377 139 H350Z" fill="#f8ecca"/>
    <path d="M107 115 H300 M190 108 V144" stroke="#3e554b" strokeWidth="2" opacity=".6"/>
    <path d="M203 114 H221 M134 114 H150" stroke="#d5ddd6" strokeWidth="3"/>
    <path d="M39 148 H378" stroke="#293e34" strokeWidth="6"/>
    {[105, 317].map(x => <g key={x}><circle cx={x} cy="150" r="27" fill="#24332d"/><circle cx={x} cy="150" r="17" fill="#b6bdb5"/><circle cx={x} cy="150" r="11" fill="#6c7b71"/><circle cx={x} cy="150" r="4" fill="#dce1d7"/></g>)}
  </svg>;
}
