import {readFile,writeFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
if(!process.argv[2])throw Error('Usage: node tools/sync-catalog.mjs /path/to/wirewalk-orders-worker/src/catalog.js');
const {CATALOG,fmt}=await import(pathToFileURL(process.argv[2]));
const items=Object.entries(CATALOG).filter(([,i])=>i.practice==='research').map(([sku,i])=>({sku,name:i.name,blurb:i.blurb,amount:i.amount,price:fmt(i.amount),priceOnApplication:!!i.priceOnApplication,group:i.group}));
if(items.length!==7)throw Error('Unexpected research service count');
await writeFile('_data/services.json',JSON.stringify(items,null,2)+'\n');
console.log('Synced 7 research services from authoritative backend catalog.');
