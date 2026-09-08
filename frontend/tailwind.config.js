export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        field: { 50:'#f0f7f1',100:'#dcedde',600:'#2f7d40',700:'#256232',800:'#1e4f29',900:'#173d20' },
        earth: { 100:'#efe7db',600:'#8a6d4b',700:'#6f5638' },
      },
      fontFamily: { display: ['Poppins','system-ui','sans-serif'], body: ['Inter','system-ui','sans-serif'] },
    },
  },
  plugins: [],
}
