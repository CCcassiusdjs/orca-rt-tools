#include <ucx.h>

void task_posi(void)
{
  
  while (1) tprintf("tick\n");
}

void task_fbu1(void)
{
  
  while (1) tprintf("tick\n");
}

void task_vod1(void)
{
  
  while (1) tprintf("tick\n");
}

void task_bfe1(void)
{
  
  while (1) tprintf("tick\n");
}

void task_vibs(void)
{
  
  while (1) tprintf("tick\n");
}

void task_bfe5(void)
{
  
  while (1) tprintf("tick\n");
}

void task_tprc(void)
{
  
  while (1) tprintf("tick\n");
}

void task_fbu5(void)
{
  
  while (1) tprintf("tick\n");
}

void task_obmg(void)
{
  
  while (1) tprintf("tick\n");
}

void task_fbu2(void)
{
  
  while (1) tprintf("tick\n");
}

void task_navc(void)
{
  
  while (1) tprintf("tick\n");
}

void task_bfe2(void)
{
  
  while (1) tprintf("tick\n");
}

void task_fdf1(void)
{
  
  while (1) tprintf("tick\n");
}

void task_bfe6(void)
{
  
  while (1) tprintf("tick\n");
}

void task_stac(void)
{
  
  while (1) tprintf("tick\n");
}

void task_fbu6(void)
{
  
  while (1) tprintf("tick\n");
}

void task_obdb(void)
{
  
  while (1) tprintf("tick\n");
}

void task_fbu3(void)
{
  
  while (1) tprintf("tick\n");
}

void task_fdf2(void)
{
  
  while (1) tprintf("tick\n");
}

void task_bfe3(void)
{
  
  while (1) tprintf("tick\n");
}

void task_stph(void)
{
  
  while (1) tprintf("tick\n");
}

void task_bfe7(void)
{
  
  while (1) tprintf("tick\n");
}

void task_spes(void)
{
  
  while (1) tprintf("tick\n");
}

void task_fbu7(void)
{
  
  while (1) tprintf("tick\n");
}

void task_usos(void)
{
  
  while (1) tprintf("tick\n");
}

void task_tpms(void)
{
  
  while (1) tprintf("tick\n");
}

void task_fbu4(void)
{
  
  while (1) tprintf("tick\n");
}

void task_thrc(void)
{
  
  while (1) tprintf("tick\n");
}

void task_bfe4(void)
{
  
  while (1) tprintf("tick\n");
}

void task_vod2(void)
{
  
  while (1) tprintf("tick\n");
}

void task_bfe8(void)
{
  
  while (1) tprintf("tick\n");
}

void task_dirc(void)
{
  
  while (1) tprintf("tick\n");
}

void task_fbu8(void)
{
  
  while (1) tprintf("tick\n");
}


int32_t app_main(void){

  switch (ucx_noc_cpu_id()){
    case 0: //   POSI,FBU1
      ucx_task_add(task_posi, "POSI", DEFAULT_STACK_SIZE,0,0,0);
      ucx_task_add(task_fbu1, "FBU1", DEFAULT_STACK_SIZE,0,0,0);
      break;
    case 1: //   VOD1,BFE1
      ucx_task_add(task_vod1, "VOD1", DEFAULT_STACK_SIZE,0,0,0);
      ucx_task_add(task_bfe1, "BFE1", DEFAULT_STACK_SIZE,0,0,0);
      break;
    case 2: //   VIBS,BFE5
      ucx_task_add(task_vibs, "VIBS", DEFAULT_STACK_SIZE,0,0,0);
      ucx_task_add(task_bfe5, "BFE5", DEFAULT_STACK_SIZE,0,0,0);
      break;
    case 3: //   TPRC,FBU5
      ucx_task_add(task_tprc, "TPRC", DEFAULT_STACK_SIZE,0,0,0);
      ucx_task_add(task_fbu5, "FBU5", DEFAULT_STACK_SIZE,0,0,0);
      break;
    case 4: //   OBMG,FBU2
      ucx_task_add(task_obmg, "OBMG", DEFAULT_STACK_SIZE,0,0,0);
      ucx_task_add(task_fbu2, "FBU2", DEFAULT_STACK_SIZE,0,0,0);
      break;
    case 5: //   NAVC,BFE2
      ucx_task_add(task_navc, "NAVC", DEFAULT_STACK_SIZE,0,0,0);
      ucx_task_add(task_bfe2, "BFE2", DEFAULT_STACK_SIZE,0,0,0);
      break;
    case 6: //   FDF1,BFE6
      ucx_task_add(task_fdf1, "FDF1", DEFAULT_STACK_SIZE,0,0,0);
      ucx_task_add(task_bfe6, "BFE6", DEFAULT_STACK_SIZE,0,0,0);
      break;
    case 7: //   STAC,FBU6
      ucx_task_add(task_stac, "STAC", DEFAULT_STACK_SIZE,0,0,0);
      ucx_task_add(task_fbu6, "FBU6", DEFAULT_STACK_SIZE,0,0,0);
      break;
    case 8: //   OBDB,FBU3
      ucx_task_add(task_obdb, "OBDB", DEFAULT_STACK_SIZE,0,0,0);
      ucx_task_add(task_fbu3, "FBU3", DEFAULT_STACK_SIZE,0,0,0);
      break;
    case 9: //   FDF2,BFE3
      ucx_task_add(task_fdf2, "FDF2", DEFAULT_STACK_SIZE,0,0,0);
      ucx_task_add(task_bfe3, "BFE3", DEFAULT_STACK_SIZE,0,0,0);
      break;
    case 10: //   STPH,BFE7
      ucx_task_add(task_stph, "STPH", DEFAULT_STACK_SIZE,0,0,0);
      ucx_task_add(task_bfe7, "BFE7", DEFAULT_STACK_SIZE,0,0,0);
      break;
    case 11: //   SPES,FBU7
      ucx_task_add(task_spes, "SPES", DEFAULT_STACK_SIZE,0,0,0);
      ucx_task_add(task_fbu7, "FBU7", DEFAULT_STACK_SIZE,0,0,0);
      break;
    case 12: //   USOS,TPMS,FBU4
      ucx_task_add(task_usos, "USOS", DEFAULT_STACK_SIZE,0,0,0);
      ucx_task_add(task_tpms, "TPMS", DEFAULT_STACK_SIZE,0,0,0);      
      ucx_task_add(task_fbu4, "FBU4", DEFAULT_STACK_SIZE,0,0,0);
      break;
    case 13: //   THRC,BFE4
      ucx_task_add(task_thrc, "THRC", DEFAULT_STACK_SIZE,0,0,0);
      ucx_task_add(task_bfe4, "BFE4", DEFAULT_STACK_SIZE,0,0,0);
      break;
    case 14: //   VOD2,BFE8
      ucx_task_add(task_vod2, "VOD2", DEFAULT_STACK_SIZE,0,0,0);
      ucx_task_add(task_bfe8, "BFE8", DEFAULT_STACK_SIZE,0,0,0);
      break;
    case 15: //   DIRC,FBU8
      ucx_task_add(task_dirc, "DIRC", DEFAULT_STACK_SIZE,0,0,0);
      ucx_task_add(task_fbu8, "FBU8", DEFAULT_STACK_SIZE,0,0,0);
      break;
    default: // 
      break;
  }

	return 1;
}
