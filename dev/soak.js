// 临时:平衡性压力测试,跑大量赛季看胜率
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const html = fs.readFileSync(path.join(__dirname, "..", "owcs-manager.html"), "utf8");
const blocks = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(x => x[1]);
const code = blocks.filter(b => b.includes("const HEROES")).pop();

function makeEl(id){return{id,innerHTML:"",textContent:"",value:"",scrollTop:0,style:{},className:"",files:[],click(){},focus(){},appendChild(){},querySelector(){return makeEl("q")},classList:{add(){},remove(){},contains(){return false}}};}
const els={}, store=new Map();
const sandbox = {
  console, Date, Math, JSON, isNaN, parseInt, parseFloat, RegExp, Error,
  setTimeout:(fn)=>{fn();return 0;}, clearTimeout:()=>{}, setInterval:()=>0, clearInterval:()=>{},
  alert:()=>{}, confirm:()=>true,
  document:{getElementById:(id)=>(els[id]=els[id]||makeEl(id)),querySelector:()=>makeEl("q"),createElement:(t)=>makeEl(t),write(){},close(){}},
  localStorage:{getItem:(k)=>store.has(k)?store.get(k):null,setItem:(k,v)=>store.set(k,String(v)),removeItem:(k)=>store.delete(k)},
  URL:{createObjectURL:()=>"blob:x"}, Blob:function(){},
};
sandbox.window=sandbox; sandbox.self=sandbox; sandbox.globalThis=sandbox;
const ctx = vm.createContext(sandbox);
vm.runInContext(code, ctx, { filename: "game.js" });

const SOAK = `
(function(){
  var ROUNDS = 260;
  var out = [];
  for (var d = 0; d <= 2; d++) {
    var wins = 0, mySum = 0, oppSum = 0, mapWins = 0, mapTotal = 0;
    for (var i = 0; i < ROUNDS; i++) {
      hardReset();
      S.difficulty = d;
      S.teamName = "AUTO";
      startDraft();
      // 贪心建队: 每次选当前能买得起的最高分
      var guard = 0;
      while (S.roster.length < 5 && guard++ < 40) {
        var need = roleNeeds();
        var role = Object.keys(need).filter(function(r){ return need[r] > 0; })[0];
        if (!role) break;
        var cand = P_CARDS.filter(function(p){
          return p.role === role && canPick(p);
        }).sort(function(a,b){ return overall(b) - overall(a); })[0];
        if (!cand) break;
        draftPick(cand.id);
      }
      startSeries();
      var g = 0;
      while (S.myMaps < 2 && S.oppMaps < 2 && g++ < 5) {
        S.phase = "series";
        beginMapSelect();
        var mg = 0;
        while (S.phase === "mapselect" && mg++ < 8) {
          if (S.aiPick) { commitMap(S.aiPick.map, S.aiPick.side === "atk" ? "def" : "atk"); }
          else if (S.pickFor === "me") {
            var opts = mapOptions(S.pickGroups);
            if (!opts.length) break;
            pickMap(opts[0].maps[0].name, "def");
          } else break;
        }
        if (!S.curMap) break;
        var bg = 0;
        while (S.phase === "ban" && bg++ < 8) {
          if (nextBanSide() === "me") {
            var cand = HEROES.filter(function(h){ return banLegalFor(h, "me"); });
            if (!cand.length) break;
            doBan(cand[0].name);
          } else aiBan();
        }
        // 用和 AI 一样的"贴合度 + 地图契合"口径挑体系,再看双方谁更吃亏
        var ARCH = ["dive","brawl","poke"];
        var best = ARCH.slice().sort(function(a,b){
          return (archFit(S.roster,b) + MODE_AFFINITY[S.curMap.mode][b]*8)
               - (archFit(S.roster,a) + MODE_AFFINITY[S.curMap.mode][a]*8);
        })[0];
        pickArch(best);
        if (S.phase === "lineup") startMatch();
        if (!S.curMapResult) break;
        mySum += S.curMapResult.myPower;
        oppSum += S.curMapResult.oppPower;
        mapTotal++;
        if (S.curMapResult.win) mapWins++;
        afterMap();
      }
      if (S.myMaps > S.oppMaps) wins++;
    }
    out.push({
      difficulty: ["轻松","标准","地狱"][d],
      seriesWin: (wins/ROUNDS*100).toFixed(1) + "%",
      mapWin: (mapWins/mapTotal*100).toFixed(1) + "%",
      myPower: (mySum/mapTotal).toFixed(1),
      oppPower: (oppSum/mapTotal).toFixed(1)
    });
  }
  return out;
})();
`;
console.log(vm.runInContext(SOAK, ctx, { filename: "soak.js" }));
